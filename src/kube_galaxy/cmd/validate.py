"""Validate command handler."""

from pathlib import Path

import typer  # type: ignore[import-not-found]
import yaml

from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.validator import validate_manifest
from kube_galaxy.pkg.utils.logging import error, info, section, success, warning


def validate_all() -> None:
    """Validate all cluster manifests."""
    validate_manifests_cmd()


def validate_manifests_cmd() -> None:
    """Validate all cluster manifests."""
    section("Validating Cluster Manifests")

    manifest_dir = Path("manifests")
    if not manifest_dir.exists():
        warning("No manifests directory found, skipping...")
        return

    manifest_files = list(manifest_dir.glob("*.yaml"))
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
