"""Test command handler."""

import shutil
import subprocess
from pathlib import Path

import typer

from kube_galaxy.cmd.validate import validate_manifests_cmd
from kube_galaxy.pkg.cluster import setup_cluster
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.testing.spread import collect_test_results, run_spread_tests
from kube_galaxy.pkg.utils.logging import error, exception, info, section, success


def local() -> None:
    """Run local validation tests without creating clusters."""
    section("Running Local Validation Tests")

    # Check required tools
    info("Checking required tools...")
    try:
        if not shutil.which("spread"):
            error("spread not found")
            raise typer.Exit(code=1)
        success("Required tools are available")
    except Exception as e:
        exception("Tool check failed", e)
        raise typer.Exit(code=1) from e

    # Validate manifests
    info("")
    validate_manifests_cmd()

    success("All local tests passed!")


def spread() -> None:
    """Run spread tests locally (requires active cluster)."""
    section("Running Spread Tests")

    try:
        # Check if kubectl can connect
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error("No Kubernetes cluster available. Please set up a cluster first.")
            info("You can create a test cluster with: kube-galaxy test setup")
            raise typer.Exit(code=1)

        # Get cluster context
        result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            text=True,
            check=True,
        )
        cluster_context = result.stdout.strip()
        success(f"Connected to cluster: {cluster_context}")

        # Run spread tests from manifest
        manifests = list(Path("manifests").glob("*.yaml"))
        if not manifests:
            error("No manifest files found")
            raise typer.Exit(code=1)
        manifest_file = str(manifests[0])

        run_spread_tests(manifest_file, test_type="functional", work_dir=".")

        # Collect test results
        results_file = collect_test_results(".")
        if results_file:
            info(f"Test results: {results_file}")

        success("Spread tests completed")

    except Exception as e:
        exception("Spread tests failed", e)
        raise typer.Exit(code=1) from e


def setup(manifest_path: str | None = None) -> None:
    """Set up cluster from manifest."""
    section("Setting Up Cluster")

    # Use provided manifest or find baseline manifest
    if manifest_path:
        manifest_file = manifest_path
        if not Path(manifest_file).exists():
            error(f"Manifest file does not exist: {manifest_file}")
            raise typer.Exit(code=1)
    else:
        manifests = list(Path("manifests").glob("*.yaml"))
        if not manifests:
            error("No manifest files found")
            raise typer.Exit(code=1)
        manifest_file = str(manifests[0])

    info(f"Using manifest: {manifest_file}")

    try:
        setup_cluster(manifest_file, work_dir=".", debug=False)
        success("Cluster setup completed")
    except Exception as e:
        exception("Cluster setup failed", e)
        raise typer.Exit(code=1) from e


def manifest(manifest_path: str) -> None:
    """Test and inspect a specific manifest file."""
    section(f"Inspecting Manifest: {manifest_path}")

    try:
        manifest_file = Path(manifest_path)
        if not manifest_file.exists():
            error(f"Manifest file does not exist: {manifest_path}")
            raise typer.Exit(code=1)

        # Load manifest
        manifest = load_manifest(manifest_file)

        # Display manifest details
        info("")
        info("Manifest Details:")
        info(f"  Name: {manifest.name}")
        info(f"  Description: {manifest.description}")
        info(f"  Kubernetes Version: {manifest.kubernetes_version}")
        info(f"  Components: {len(manifest.components)}")
        if manifest.components:
            info("    - " + ", ".join(c.name for c in manifest.components))
        info(f"  Networking: {len(manifest.networking)}")

        success("Manifest is valid!")

    except Exception as e:
        exception("Failed to inspect manifest", e)
        raise typer.Exit(code=1) from e
