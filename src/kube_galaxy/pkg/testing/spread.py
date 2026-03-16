"""Spread test execution and management."""

import os
import shutil
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import yaml

from kube_galaxy.pkg.arch.detector import get_arch_info
from kube_galaxy.pkg.literals import SystemPaths, Timeouts
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import ComponentConfig, Manifest
from kube_galaxy.pkg.manifest.validator import (
    get_components_with_spread,
    validate_component_test_structure,
)
from kube_galaxy.pkg.utils.client import create_namespace, delete_namespace, verify_connectivity
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import error, info, section, success, warning
from kube_galaxy.pkg.utils.shell import ShellError, run


class SpreadYamlDumper(yaml.SafeDumper):
    """Custom YAML dumper to handle Path objects as strings."""

    pass


# Register custom representer for Path objects to dump as strings
SpreadYamlDumper.add_multi_representer(Path, lambda d, p: d.represent_str(str(p)))


@contextmanager
def _setup_shared_kubeconfig() -> Generator[Path, None, None]:
    """
    Context manager to copy kubeconfig to shared directory and clean up after.

    Yields:
        Path to the shared kubeconfig file accessible by LXD containers

    Note:
        The kubeconfig is copied to SystemPaths.tests_root() which is mounted
        in spread's LXD containers, allowing tests to access the cluster.
    """
    # Copy kubeconfig to shared test directory for LXD container access
    source_kubeconfig = os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))
    shared_kubeconfig = SystemPaths.tests_root() / "kubeconfig"

    # Ensure test root directory exists
    SystemPaths.tests_root().mkdir(parents=True, exist_ok=True)

    try:
        info(f"Setting up shared kubeconfig from {source_kubeconfig}")
        shutil.copy2(source_kubeconfig, shared_kubeconfig)
        success(f"Kubeconfig copied to {shared_kubeconfig}")
        yield shared_kubeconfig
    finally:
        # Cleanup: remove the copied kubeconfig
        if shared_kubeconfig.exists():
            info(f"Cleaning up shared kubeconfig: {shared_kubeconfig}")
            shared_kubeconfig.unlink()
            success("Shared kubeconfig removed")


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

        # Setup shared kubeconfig and run tests (cleanup handled by context manager)
        with _setup_shared_kubeconfig() as kubeconfig:
            # Run tests from components with spread enabled
            _run_component_tests(manifest, work_dir_path, test_type, debug, kubeconfig)

        section("Test Execution Complete")
        success("Tests completed successfully")

    except Exception as exc:
        raise ClusterError(f"Test execution failed: {exc}") from exc


def _verify_test_prerequisites() -> None:
    """Verify kubectl and spread are available."""
    try:
        verify_connectivity()

        # Check for spread
        info("Verifying spread test framework...")
        result = run(["which", "spread"], check=True, capture_output=True)
        spread_path = result.stdout.strip()
        success(f"Found spread at {spread_path}")

        # Check for lxclient (required by spread)
        info("Verifying lxclient (required by spread)...")
        result = run(["which", "lxc"], check=True, capture_output=True)
        lxclient_path = result.stdout.strip()
        success(f"Found lxclient at {lxclient_path}")

    except ShellError as exc:
        raise ClusterError("Test prerequisites not met") from exc


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

    labels = {
        "app.kubernetes.io/managed-by": "kube-galaxy",
        "component": component_name,
    }
    create_namespace(namespace, labels)
    return namespace


def _generate_orchestration_spread_yaml(
    components: list[ComponentConfig], kubeconfig: Path
) -> list[str]:
    """
    Generate spread.yaml from template for component test orchestration.

    Args:
        components: List of components with spread tests
        kubeconfig: Path to kubeconfig file (in shared directory)

    Returns:
        List of component suites

    Raises:
        ClusterError: If generation fails
    """
    try:
        info("Generating test orchestration spread.yaml...")
        # Get architecture info
        arch_info = get_arch_info()

        # Load template
        suites = {}
        spread_def = {
            "path": SystemPaths.tests_root(),
            "environment": {
                "PROJECT_PATH": SystemPaths.tests_root(),
                "TEST_TIMEOUT_S": str(Timeouts.TEST_EXECUTION_TIMEOUT_S),
                "TEST_TIMEOUT_M": str(Timeouts.TEST_EXECUTION_TIMEOUT_S // 60),
                "KUBECONFIG": str(kubeconfig),
                "SYSTEM_ARCH": arch_info.system,
                "K8S_ARCH": arch_info.k8s,
                "IMAGE_ARCH": arch_info.image,
            },
        }

        # Generate component suites section.
        # By the time tests run, all task definitions are installed under tests_root
        for each in components:
            suite_path = SystemPaths.tests_component_root(each.name)
            task = suite_path / "task.yaml"
            suite = yaml.safe_load(task.read_text())  # Load for name and summary
            rel = suite_path.relative_to(SystemPaths.tests_root()).parent
            suites[f"{rel}/"] = {
                "summary": suite.get("summary", "No summary"),
                # Per-suite environment variables are forwarded to each task's
                # `execute` block by spread, allowing task.yaml files to reference
                # $COMPONENT_NAME and $COMPONENT_VERSION as shell variables.
                "environment": {
                    "COMPONENT_NAME": each.name,
                    "COMPONENT_VERSION": each.release,
                },
            }

        spread_def["suites"] = suites

        # Read template spread.yaml.tmpl
        template_path = Path(__file__).parent / "templates/spread.yaml.tmpl"
        content = yaml.safe_load(template_path.read_text())

        # Update template with generated suites and environment
        content.update(spread_def)

        # Write spread.yaml
        output_path = SystemPaths.tests_spread_yaml()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        yaml.dump(content, output_path.open("w"), Dumper=SpreadYamlDumper)
        success(f"Generated: {output_path}")
        return list(suites.keys())

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

        # Build environment with test context
        env = os.environ.copy()
        env.update(
            {
                "KUBE_GALAXY_NAMESPACE": namespace,
                "COMPONENT_NAME": component.name,
                "COMPONENT_VERSION": component.release,
            }
        )

        # Only run spread for the kube-galaxy-task within the component suite
        cmd = ["spread", "-v", f"{suite_path}/kube-galaxy"]

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
            success(f"  Tests passed for {component.name}")
        else:
            error(f"  Tests failed for {component.name} (exit code: {result.returncode})")
            error(f"  Log file: {log_file}")
        return result.returncode == 0

    except Exception as exc:
        error(f"  Test execution error: {exc}")
        return False


def _run_component_tests(
    manifest: Manifest, work_dir: Path, test_type: str, debug: bool, kubeconfig: Path
) -> None:
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
    component_suites = _generate_orchestration_spread_yaml(spread_components, kubeconfig)

    # Track test results
    test_results = []

    # Run tests for each component sequentially
    for i, (component, suite) in enumerate(
        zip(spread_components, component_suites, strict=False), 1
    ):
        section(f"Testing Component [{i}/{len(spread_components)}]: {component.name}")
        info(f"  Release: {component.release}")
        info(f"  Repo: {component.test.repo.base_url}")

        # Component-specific directories
        log_dir = work_dir / "logs" / component.name
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "test-output.log"

        namespace = None
        test_passed = False

        try:
            # Step 2: Create test namespace
            namespace = _create_test_namespace(component.name)

            # Step 3: Execute spread tests
            test_passed = _execute_spread_for_component(
                component,
                namespace,
                SystemPaths.tests_spread_yaml(),
                Path(suite),
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
            error(f"Test execution failed: {exc}")
            test_results.append(
                {
                    "component": component.name,
                    "result": "failed",
                    "error": str(exc),
                    "log": str(log_file) if log_file.exists() else "",
                }
            )

        finally:
            # Step 4: Cleanup namespace (always executed)
            if namespace:
                try:
                    delete_namespace(namespace)
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
        section("Failed components")
        for result in test_results:
            if result["result"] != "passed":
                error(f"- {result['component']}")
                if result.get("log"):
                    info(f" Log: {result['log']}")

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
