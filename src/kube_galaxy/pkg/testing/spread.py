"""Spread test execution and management."""

import os
import shutil
import subprocess
from pathlib import Path
from string import Template

from git import Repo
from git.exc import GitCommandError

from kube_galaxy.pkg.arch.detector import get_arch_info
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import ComponentConfig, Manifest
from kube_galaxy.pkg.manifest.validator import (
    get_components_with_spread,
    validate_component_test_structure,
)
from kube_galaxy.pkg.utils.components import format_component_pattern
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import error, info, section, success, warning
from kube_galaxy.pkg.utils.shell import ShellError, run


def run_spread_tests(
    manifest_path: str,
    test_type: str = "functional",
    work_dir: str = ".",
    debug: bool = False,
) -> None:
    """
    Execute spread tests from components with test enabled.

    Args:
        manifest_path: Path to cluster manifest YAML
        test_type: Test type to run (e.g., 'functional', 'integration')
        work_dir: Working directory for test results
        debug: Enable debug output

    Raises:
        ClusterError: If test execution fails
    """
    try:
        # Load and validate manifest
        manifest = load_manifest(manifest_path)
        work_dir_path = Path(work_dir)

        section("Running Tests")
        info(f"Manifest: {manifest_path}")
        info(f"Test Type: {test_type}")
        info(f"Work Dir: {work_dir}")

        # Verify test prerequisites (kubectl connectivity, spread availability)
        _verify_test_prerequisites()

        # Run tests from components with spread enabled
        _run_component_tests(manifest, work_dir_path, test_type, debug)

        section("Test Execution Complete")
        success("Tests completed successfully")

    except Exception as exc:
        raise ClusterError(f"Test execution failed: {exc}") from exc


def _verify_test_prerequisites() -> None:
    """Verify kubectl and spread are available."""
    try:
        info("Verifying cluster connectivity...")
        run(["kubectl", "cluster-info"], check=True, capture_output=True)
        success("✓ Connected to Kubernetes cluster")

        # Check for spread
        info("Verifying spread test framework...")
        result = run(["which", "spread"], check=True, capture_output=True)
        spread_path = result.stdout.strip()
        success(f"✓ Found spread at {spread_path}")

    except ShellError as exc:
        if "spread" in str(exc):
            error(
                "Spread test framework not found. Install from: https://github.com/canonical/spread"
            )
        raise ClusterError("Test prerequisites not met") from exc


def _checkout_component_repo(component: ComponentConfig, dest_path: Path) -> Path | None:
    """
    Clone component repository at specified reference.

    Args:
        component: Component configuration
        dest_path: Destination path for cloned repository

    Raises:
        ClusterError: If clone or checkout fails
    """
    git_ref = format_component_pattern(
        component.repo.ref or component.release, component, get_arch_info()
    )
    try:
        # Determine git reference (use explicit ref or fall back to release)
        info(f"  Cloning {component.repo.base_url} @ {git_ref}...")

        # Remove existing directory if present
        if dest_path.exists():
            shutil.rmtree(dest_path)

        # Clone repository
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Try to clone with specific branch/tag
            Repo.clone_from(component.repo.base_url, dest_path, depth=1, branch=git_ref)
        except GitCommandError:
            # If branch doesn't work, clone and checkout (handles commits)
            info("  Branch checkout failed, trying commit checkout...")
            repo = Repo.clone_from(component.repo.base_url, dest_path, depth=1)
            repo.git.checkout(git_ref)

        # Determine spread directory location
        tasks = Path("spread/kube-galaxy")
        if component.repo.subdir:
            # Monorepo: look in subdirectory
            tasks_dir = dest_path / component.repo.subdir / tasks
            info(f"  Using monorepo subdirectory: {component.repo.subdir}")
        else:
            # Standard repo: look at root
            tasks_dir = dest_path / tasks

        if not tasks_dir.exists():
            error(
                f"Component {component.name} does not have directory "
                f"at {tasks_dir.relative_to(dest_path)}"
            )
            return None

        success(f"  ✓ Repository ready at {dest_path}")
        if component.repo.subdir:
            info(f"  ✓ Tests found in {tasks_dir.relative_to(dest_path)}")
        return dest_path

    except GitCommandError as exc:
        raise ClusterError(
            f"Failed to clone {component.repo.base_url} at {git_ref}: {exc}"
        ) from exc
    except Exception as exc:
        raise ClusterError(f"Failed to checkout component repo: {exc}") from exc


def _create_test_namespace(component_name: str) -> str:
    """
    Create Kubernetes namespace for component tests.

    Args:
        component_name: Name of component being tested

    Returns:
        Namespace name

    Raises:
        ClusterError: If namespace creation fails
    """
    # Normalize component name for namespace (lowercase, hyphens only)
    namespace = f"kube-galaxy-test-{component_name.lower().replace('_', '-')}"

    try:
        info(f"  Creating test namespace: {namespace}")

        # Create namespace with labels
        run(
            [
                "kubectl",
                "create",
                "namespace",
                namespace,
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            check=True,
            capture_output=True,
        )

        # Apply with labels
        run(
            [
                "kubectl",
                "create",
                "namespace",
                namespace,
                "-o",
                "json",
            ],
            check=True,
            capture_output=True,
        )

        # Label namespace
        run(
            [
                "kubectl",
                "label",
                "namespace",
                namespace,
                "app.kubernetes.io/managed-by=kube-galaxy",
                f"component={component_name}",
            ],
            check=True,
            capture_output=True,
        )

        success(f"  ✓ Namespace created: {namespace}")
        return namespace

    except ShellError as exc:
        raise ClusterError(f"Failed to create namespace {namespace}: {exc}") from exc


def _cleanup_test_namespace(namespace: str, timeout: int = 60) -> None:
    """
    Delete test namespace and wait for termination.

    Args:
        namespace: Namespace to delete
        timeout: Maximum seconds to wait for deletion

    Raises:
        ClusterError: If namespace deletion fails
    """
    try:
        info(f"  Cleaning up namespace: {namespace}")

        # Delete namespace
        run(
            ["kubectl", "delete", "namespace", namespace, "--timeout", f"{timeout}s"],
            check=True,
            capture_output=True,
        )

        success(f"  ✓ Namespace deleted: {namespace}")

    except ShellError as exc:
        # Don't fail if namespace doesn't exist
        if "not found" in str(exc):
            warning(f"  Namespace {namespace} not found (may already be deleted)")
        else:
            raise ClusterError(f"Failed to delete namespace {namespace}: {exc}") from exc


def _generate_orchestration_spread_yaml(
    manifest: Manifest,
    components: list[ComponentConfig],
) -> Path:
    """
    Generate spread.yaml from template for component test orchestration.

    Args:
        manifest: Cluster manifest
        components: List of components with spread tests

    Returns:
        Path to generated spread.yaml

    Raises:
        ClusterError: If generation fails
    """
    try:
        info("Generating test orchestration spread.yaml...")

        # Load template
        template_path = Path(__file__).parent / "spread.yaml.tmpl"
        template_content = template_path.read_text()

        # Get architecture info
        arch_info = get_arch_info()

        # Get kubeconfig path
        kubeconfig = os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))

        # Generate component suites section
        component_suites = []
        for component in components:
            if component.repo.subdir:
                suite_path = (
                    f"  {component.name}/origin/{component.repo.subdir}/spread/kube-galaxy/:"
                )
            else:
                suite_path = f"  {component.name}/origin/spread/kube-galaxy/:"
            component_suites.append(suite_path)

        # Fill template
        template = Template(template_content)
        spread_yaml_content = template.substitute(
            test_root_path=SystemPaths.KUBE_GALAXY_TESTS_ROOT,
            kubeconfig_path=kubeconfig,
            namespace="PLACEHOLDER",  # Will be overridden per component
            system_arch=arch_info.system,
            k8s_arch=arch_info.k8s,
            image_arch=arch_info.image,
            component_name="PLACEHOLDER",  # Will be overridden per component
            component_version="PLACEHOLDER",  # Will be overridden per component
            component_suites="\n".join(component_suites),
        )

        # Write spread.yaml
        output_path = SystemPaths.tests_spread_yaml()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(spread_yaml_content)
        success(f"  ✓ Generated: {output_path}")
        return output_path

    except Exception as exc:
        raise ClusterError(f"Failed to generate spread.yaml: {exc}") from exc


def _execute_spread_for_component(
    component: ComponentConfig,
    namespace: str,
    spread_yaml: Path,
    suite_path: Path,
    log_file: Path,
) -> bool:
    """
    Execute spread tests for a component.

    Args:
        component: Component configuration
        namespace: Kubernetes namespace for tests
        spread_yaml: Path to orchestration spread.yaml
        log_file: Path to save test output

    Returns:
        True if tests passed, False otherwise
    """
    try:
        info(f"  Executing tests for {component.name}...")

        # Get architecture info
        arch_info = get_arch_info()

        # Build environment with test context
        env = os.environ.copy()
        env.update(
            {
                "KUBE_GALAXY_NAMESPACE": namespace,
                "COMPONENT_NAME": component.name,
                "COMPONENT_VERSION": component.release,
                "SYSTEM_ARCH": arch_info.system,
                "K8S_ARCH": arch_info.k8s,
                "IMAGE_ARCH": arch_info.image,
            }
        )

        cmd = ["spread", "-v", f"adhoc:{suite_path}"]

        info(f"  Command: {' '.join(cmd)}")
        info(f"  Working directory: {spread_yaml.parent}")

        # Run spread and capture output
        with open(log_file, "w") as log:
            result = subprocess.run(
                cmd,
                cwd=spread_yaml.parent,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

        if result.returncode == 0:
            success(f"  ✓ Tests passed for {component.name}")
        else:
            error(f"  ✗ Tests failed for {component.name} (exit code: {result.returncode})")
            error(f"  Log file: {log_file}")
        return result.returncode == 0

    except Exception as exc:
        error(f"  ✗ Test execution error: {exc}")
        return False


def _run_component_tests(manifest: Manifest, work_dir: Path, test_type: str, debug: bool) -> None:
    """Run spread tests from components marked with test: true."""
    section("Looking for components with spread tests")

    # Get components with spread tests enabled
    spread_components = get_components_with_spread(manifest)

    if not spread_components:
        warning("No components with spread tests enabled")
        return

    info(f"Found {len(spread_components)} component(s) with tests enabled")

    # Validate components have proper structure for testing
    validation_errors = []
    for component in spread_components:
        if errors := validate_component_test_structure(component):
            validation_errors.extend(errors)

    if validation_errors:
        error("Component validation failed:")
        for err in validation_errors:
            error(f"  - {err}")
        raise ClusterError("Component validation failed")

    # Generate orchestration spread.yaml
    try:
        spread_yaml = _generate_orchestration_spread_yaml(manifest, spread_components)
    except ClusterError as exc:
        error(f"Failed to generate orchestration spread.yaml: {exc}")
        raise

    # Track test results
    test_results = []

    # Run tests for each component sequentially
    for i, component in enumerate(spread_components, 1):
        section(f"Testing Component [{i}/{len(spread_components)}]: {component.name}")
        info(f"  Release: {component.release}")
        info(f"  Repo: {component.repo.base_url}")

        # Component-specific directories
        component_test_dir = SystemPaths.component_test_dir(component.name)
        log_dir = work_dir / "logs" / component.name
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "test-output.log"

        namespace = None
        test_passed = False

        try:
            # Step 1: Checkout component repository
            suite_dir = _checkout_component_repo(component, component_test_dir)
            if suite_dir is None:
                error(f"  ✗ Skipping tests for {component.name} due to missing test directory")
                test_results.append(
                    {
                        "component": component.name,
                        "result": "skipped",
                        "error": "Missing test directory",
                    }
                )
                continue

            # Step 2: Create test namespace
            namespace = _create_test_namespace(component.name)

            # Step 3: Execute spread tests
            test_passed = _execute_spread_for_component(
                component,
                namespace,
                spread_yaml,
                suite_dir,
                log_file,
            )

            # Record result
            test_results.append(
                {
                    "component": component.name,
                    "result": "passed" if test_passed else "failed",
                    "log": str(log_file),
                }
            )

        except Exception as exc:
            error(f"  ✗ Test execution failed: {exc}")
            test_results.append(
                {
                    "component": component.name,
                    "result": "failed",
                    "error": str(exc),
                    "log": str(log_file) if log_file.exists() else None,
                }
            )

        finally:
            # Step 4: Cleanup namespace (always executed)
            if namespace:
                try:
                    _cleanup_test_namespace(namespace)
                except Exception as cleanup_exc:
                    warning(f"  Namespace cleanup failed: {cleanup_exc}")

    # Summary
    section("Test Results Summary")
    passed = sum(1 for r in test_results if r["result"] == "passed")
    skipped = sum(1 for r in test_results if r["result"] == "skipped")
    failed = sum(1 for r in test_results if r["result"] == "failed")

    info(f"Total: {len(test_results)}")
    success(f"Passed: {passed}")
    if skipped:
        warning(f"Skipped: {skipped}")
    if failed > 0:
        error(f"Failed: {failed}")

    # Show failed components
    if failed > 0:
        info("\nFailed components:")
        for result in test_results:
            if not result["passed"]:
                error(f"  - {result['component']}")
                if result.get("log"):
                    info(f"    Log: {result['log']}")

        raise ClusterError(f"{failed} component test(s) failed")

    success("All component tests passed or skipped!")


def collect_test_results(work_dir: str = ".") -> str | None:
    """
    Collect test results from work directory.

    Args:
        work_dir: Working directory containing test results

    Returns:
        Path to consolidated test results file or None if no results
    """
    work_dir_path = Path(work_dir)
    logs_dir = work_dir_path / "logs"

    if not logs_dir.exists():
        warning(f"No test logs found in {logs_dir}")
        return None

    # Collect results from all components
    results_summary = work_dir_path / "logs" / "summary.txt"

    try:
        with open(results_summary, "w") as f:
            f.write("Component Test Results Summary\n")
            f.write("=" * 50 + "\n\n")

            for component_dir in sorted(logs_dir.iterdir()):
                if component_dir.is_dir():
                    f.write(f"Component: {component_dir.name}\n")

                    # Check for test output log
                    test_log = component_dir / "test-output.log"
                    if test_log.exists():
                        f.write(f"  Log: {test_log}\n")

                        # Try to determine if tests passed
                        with open(test_log) as log:
                            log_content = log.read()
                            if (
                                "successful" in log_content.lower()
                                or "passed" in log_content.lower()
                            ):
                                f.write("  Status: PASSED\n")
                            elif "failed" in log_content.lower() or "error" in log_content.lower():
                                f.write("  Status: FAILED\n")
                            else:
                                f.write("  Status: UNKNOWN\n")
                    else:
                        f.write("  Status: NO LOG FOUND\n")

                    f.write("\n")

        success(f"Test results summary: {results_summary}")
        return str(results_summary)

    except Exception as exc:
        error(f"Failed to collect test results: {exc}")
        return None
