"""Test command handler."""

from pathlib import Path

import typer
import yaml

from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import NodeRole
from kube_galaxy.pkg.manifest.validator import validate_manifest
from kube_galaxy.pkg.testing.spread import collect_test_results, run_spread_tests
from kube_galaxy.pkg.units.provider import provider_factory
from kube_galaxy.pkg.utils.client import get_context, verify_connectivity
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import error, exception, info, section, success, warning


def spread(manifest_path: str) -> None:
    """Run spread tests locally (requires active cluster)."""
    section("Running Spread Tests")

    # Validate manifests
    info("")
    validate(manifest_path)

    try:
        # Provision the orchestrator unit via the manifest's provider
        manifest = load_manifest(manifest_path)
        provider = provider_factory(manifest)
        lead_unit = provider.locate(NodeRole.CONTROL_PLANE, 0)

        # Check if kubectl can connect
        verify_connectivity(lead_unit)

        # Get cluster context
        cluster_context = get_context(lead_unit)
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

    except ClusterError as e:
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
