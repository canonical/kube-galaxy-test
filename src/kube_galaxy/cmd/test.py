"""Test command handler."""

import subprocess
from pathlib import Path

import typer
import yaml

from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.validator import validate_manifest
from kube_galaxy.pkg.testing.spread import collect_test_results, run_spread_tests
from kube_galaxy.pkg.utils.logging import error, exception, info, section, success, warning


def spread(manifest_path: str) -> None:
    """Run spread tests locally (requires active cluster)."""
    section("Running Spread Tests")

    # Validate manifests
    info("")
    validate(manifest_path)

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
            info("You can create a test cluster with: kube-galaxy setup")
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
        if not manifest_path:
            error("No manifest file provided")
            raise typer.Exit(code=1)

        run_spread_tests(manifest_path, test_type="functional", work_dir=".")

        # Collect test results
        results_file = collect_test_results(".")
        if results_file:
            info(f"Test results: {results_file}")

        success("Spread tests completed")

    except Exception as e:
        exception("Spread tests failed", e)
        raise typer.Exit(code=1) from e


def validate(manifest_path: str | None = None) -> None:
    """Validate all cluster manifests."""
    section("Validating Cluster Manifests")

    manifest_dir = Path("manifests")
    if not manifest_dir.exists():
        warning("No manifests directory found, skipping...")
        return

    if manifest_path is None:
        manifest_files = list(manifest_dir.glob("*.yaml"))
    else:
        manifest_files = [Path(manifest_path)]

    if not manifest_files:
        warning("No manifest files found in manifests/")
        return

    for manifest_file in manifest_files:
        try:
            info(f"Validating {manifest_file}...")

            # Validate YAML syntax
            with open(manifest_file) as f:
                yaml.safe_load(f)
            success(f"{manifest_file} is valid YAML")

            # Load and validate manifest
            manifest = load_manifest(manifest_file)
            validate_manifest(manifest)
            success(f"{manifest_file} has valid schema")

        except Exception as e:
            error(f"{manifest_file}: {e}")
            raise typer.Exit(code=1) from e

    success("All manifests validated successfully!")
