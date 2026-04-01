"""Spread test execution and management."""

import os
import subprocess
from pathlib import Path

import yaml

from kube_galaxy.pkg.literals import SystemPaths, TestDirectories, Timeouts
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import ComponentConfig, Manifest
from kube_galaxy.pkg.manifest.validator import (
    get_components_with_spread,
    validate_component_test_structure,
)
from kube_galaxy.pkg.units.local import LocalUnit
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import error, info, section, success, warning
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.shell import ShellError, check_installed


def _TeeRun(cmd: list[str], cwd: Path, env: dict[str, str], log_file: Path) -> int:
    """Write to a file and stdout simultaneously."""
    with log_file.open("w") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # line-buffered
        )
        if proc.stdout is None:
            raise ClusterError("Failed to capture subprocess output")

        for line in iter(proc.stdout.readline, ""):
            print(line, end="")
            log.write(line)

        proc.stdout.close()
        return proc.wait()


class SpreadYamlDumper(yaml.SafeDumper):
    """Custom YAML dumper to handle Path objects as strings."""

    pass


# Register custom representer for Path objects to dump as strings
SpreadYamlDumper.add_multi_representer(Path, lambda d, p: d.represent_str(str(p)))


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
        _print_dependency_status()

        # Run tests from components with spread enabled
        _run_component_tests(manifest, work_dir_path, test_type, debug)

        section("Test Execution Complete")
        success("Tests completed successfully")

    except Exception as exc:
        raise ClusterError(f"Test execution failed: {exc}") from exc


def _print_dependency_status() -> None:
    """Verify spread is available."""
    try:
        # Check for spread
        info("Verifying spread test framework...")
        check_installed("spread")

        # Check for lxclient (required by spread)
        info("Verifying lxclient (required by spread)...")
        check_installed("lxc")

    except ShellError as exc:
        raise ClusterError("Test prerequisites not met") from exc


def _component_kill_timeout(component: ComponentConfig) -> str | None:
    """Determine if a custom kill timeout is needed for the component."""
    timeout_s = component.test.environment.get("TEST_TIMEOUT_S")
    timeout_m = component.test.environment.get("TEST_TIMEOUT_M")
    buffer = 30

    if timeout_s and not timeout_m:
        return f"{int(timeout_s) + buffer}s"
    elif timeout_m and not timeout_s:
        return f"{int(timeout_m) * 60 + buffer}s"
    elif timeout_s and timeout_m and int(timeout_s) == int(timeout_m) * 60:
        return f"{int(timeout_s) + buffer}s"
    elif timeout_s and timeout_m:
        raise ClusterError(
            f"Component '{component.name}' has inconsistent test timeouts: "
            f"TEST_TIMEOUT_S={timeout_s}, TEST_TIMEOUT_M={timeout_m}"
        )

    return None


def _generate_orchestration_spread_yaml(
    components: list[ComponentConfig], k8s_version: str
) -> list[str]:
    """
    Generate spread.yaml from template for component test orchestration.

    Args:
        components: List of components with spread tests
        k8s_version: Kubernetes version for conditional test logic

    Returns:
        List of component suites

    Raises:
        ClusterError: If generation fails
    """
    try:
        info("Generating test orchestration spread.yaml...")
        # Get architecture info
        local_test = SystemPaths.local_tests_root()

        # Load template
        suites = {}
        spread_def = {
            "path": local_test,
            "kill-timeout": f"{Timeouts.TEST_EXECUTION_TIMEOUT_S + 30}s",
            "environment": {
                "PROJECT_PATH": str(local_test),
                "TEST_TIMEOUT_S": str(Timeouts.TEST_EXECUTION_TIMEOUT_S),
                "TEST_TIMEOUT_M": str(Timeouts.TEST_EXECUTION_TIMEOUT_S // 60),
                "KUBECONFIG": str(SystemPaths.local_kube_config()),
                "K8S_VERSION": k8s_version,
            },
        }

        arch_info = LocalUnit().arch

        # Generate component suites section.
        # By the time tests run, all task definitions are installed under tests_root
        for each in components:
            suite_path = SystemPaths.tests_component_root(each.name)
            task = suite_path / "task.yaml"
            suite = yaml.safe_load(task.read_text())  # Load for name and summary
            rel = suite_path.relative_to(local_test).parent
            suites[f"{rel}/"] = {
                "summary": suite.get("summary", "No summary"),
                # Per-suite environment variables are forwarded to each task's
                # `execute` block by spread, allowing task.yaml files to reference
                # $COMPONENT_NAME and $COMPONENT_VERSION as shell variables.
                "environment": {
                    "COMPONENT_NAME": each.name,
                    "COMPONENT_VERSION": each.release,
                    "SYSTEM_ARCH": arch_info.system,
                    "K8S_ARCH": arch_info.k8s,
                    "IMAGE_ARCH": arch_info.image,
                    **each.test.environment,
                },
            }
            if kill_timeout := _component_kill_timeout(each):
                info(f"Setting kill timeout for component '{each.name}' to {kill_timeout}")
                suites[f"{rel}/"]["kill-timeout"] = kill_timeout

        spread_def["suites"] = suites

        # Read template spread.yaml.tmpl
        template_path = Path(__file__).parent / "templates/spread.yaml.tmpl"
        content = yaml.safe_load(template_path.read_text())

        # Update template with generated suites and environment
        content.update(spread_def)

        # Write spread.yaml
        output_path = SystemPaths.tests_spread_yaml()
        ensure_dir(output_path.parent)
        yaml.dump(content, output_path.open("w"), Dumper=SpreadYamlDumper)
        success(f"Generated: {output_path}")
        return list(suites.keys())

    except Exception as exc:
        raise ClusterError(f"Failed to generate spread.yaml: {exc}") from exc


def _execute_spread_for_component(
    component: ComponentConfig,
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
                "COMPONENT_NAME": component.name,
                "COMPONENT_VERSION": component.release,
            }
        )

        # Only run spread for the kube-galaxy-task within the component suite
        artifacts = log_file.parent.absolute() / "artifacts"
        cmd = ["spread", "-v", f"-artifacts={artifacts}", f"{suite_path}/kube-galaxy"]

        info(f"  Command: {' '.join(cmd)}")
        info(f"  Working directory: {spread_yaml.parent}")

        # Run spread, tee output to stdout and log file
        return_code = _TeeRun(cmd, spread_yaml.parent, env, log_file)
        if return_code == 0:
            success(f"  Tests passed for {component.name}")
        else:
            error(f"  Tests failed for {component.name} (exit code: {return_code})")
            error(f"  Log file: {log_file}")
        return return_code == 0

    except Exception as exc:
        error(f"  Test execution error: {exc}")
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
    k8s_version = manifest.kubernetes_version
    component_suites = _generate_orchestration_spread_yaml(spread_components, k8s_version)

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
        log_dir = work_dir / TestDirectories.DEBUG_LOGS / component.name
        ensure_dir(log_dir)
        log_file = log_dir / "test-output.log"

        test_passed = False

        try:
            # Step 2: Execute spread tests
            test_passed = _execute_spread_for_component(
                component,
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
    logs_dir = work_dir_path / TestDirectories.DEBUG_LOGS

    if not logs_dir.exists():
        warning(f"No test logs found in {logs_dir}")
        return None

    # Collect results from all components
    results_summary = logs_dir / "spread-summary.txt"

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
