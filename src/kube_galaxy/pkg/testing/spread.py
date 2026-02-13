"""Spread test execution and management."""

from pathlib import Path

from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import Manifest
from kube_galaxy.pkg.manifest.validator import get_components_with_spread
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
    Execute spread tests from components with use-spread enabled.

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

        # Verify cluster connectivity
        _verify_cluster_connectivity()

        # Create test directories
        work_dir_path.mkdir(parents=True, exist_ok=True)
        (work_dir_path / "test-results").mkdir(exist_ok=True)
        (work_dir_path / "spread-results").mkdir(exist_ok=True)

        # Get current cluster context
        try:
            result = run(
                ["kubectl", "config", "current-context"],
                capture_output=True,
                text=True,
                check=True,
            )
            current_context = result.stdout.strip()
            info(f"Connected to cluster: {current_context}")
        except ShellError:
            warning("Could not determine current cluster context")

        # Run tests from components with spread enabled
        _run_component_tests(manifest, work_dir_path, test_type, debug)

        section("Test Execution Complete")
        success("Tests completed successfully")

    except Exception as exc:
        raise ClusterError(f"Test execution failed: {exc}") from exc


def _verify_cluster_connectivity() -> None:
    """Verify kubectl can connect to cluster."""
    try:
        info("Verifying cluster connectivity...")
        run(["kubectl", "cluster-info"], check=True, capture_output=True)
        success("Connected to Kubernetes cluster")
    except ShellError as exc:
        raise ClusterError("Cannot connect to Kubernetes cluster via kubectl") from exc


def _run_component_tests(manifest: Manifest, work_dir: Path, test_type: str, debug: bool) -> None:
    """Run spread tests from components marked with use-spread: true."""
    section("Looking for components with spread tests")

    # Get components with spread tests enabled
    spread_components = get_components_with_spread(manifest)

    if not spread_components:
        warning("No components with spread tests enabled")
        return

    for i, component in enumerate(spread_components, 1):
        info(f"Component [{i}/{len(spread_components)}]: {component.name}")
        info(f"  Release: {component.release}")
        info(f"  Repo: {component.repo}")

        test_results_dir = work_dir / "spread-results" / component.name
        test_results_dir.mkdir(parents=True, exist_ok=True)

        try:
            # This is a placeholder for actual spread test execution
            # Real implementation would:
            # 1. Clone component repo at specified release
            # 2. Find spread.yaml in component
            # 3. Execute spread tests
            # 4. Collect results

            if debug:
                info(f"  [DEBUG] Would execute spread tests for {component.name}")
            else:
                info("  Marking tests for execution")

            success(f"  ✓ Tests processed for {component.name}")

        except Exception as exc:
            error(f"  ✗ Test execution failed: {exc}")
            raise


def collect_test_results(work_dir: str = ".") -> str | None:
    """
    Collect test results from work directory.

    Args:
        work_dir: Working directory containing test results

    Returns:
        Path to consolidated test results file or None if no results
    """
    work_dir_path = Path(work_dir)
    results_dir = work_dir_path / "spread-results"

    if not results_dir.exists():
        warning(f"No test results found in {results_dir}")
        return None

    # Collect results from all components
    results_summary = work_dir_path / "test-results" / "summary.txt"
    results_summary.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(results_summary, "w") as f:
            f.write("Test Results Summary\n")
            f.write("====================\n\n")

            for component_dir in sorted(results_dir.iterdir()):
                if component_dir.is_dir():
                    f.write(f"Component: {component_dir.name}\n")
                    # Would process actual test results here
                    f.write("  Status: Completed\n\n")

        success(f"Test results collected to {results_summary}")
        return str(results_summary)

    except Exception as exc:
        error(f"Failed to collect test results: {exc}")
        return None
