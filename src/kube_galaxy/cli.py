"""Main CLI entry point for kube-galaxy."""

import sys

import typer

from kube_galaxy import __version__
from kube_galaxy.cmd import cleanup, logs, setup, status, test
from kube_galaxy.pkg.utils.paths import get_active_manifest

app = typer.Typer(
    help="Kubernetes Galaxy: Scalable Kubernetes testing infrastructure",
    invoke_without_command=False,
    no_args_is_help=True,
)

# Module-level OptionInfo objects avoid B008 (function call in default argument)
# while preserving full Typer metadata for --help, shell completion, etc.
_OVERLAY_OPTION = typer.Option(
    None,
    "--overlay",
    help=(
        "Path to an overlay YAML file to deep-merge on top of the base manifest. "
        "Repeat to apply multiple overlays in order (later overlays win)."
    ),
)
_PROVIDER_IMAGE_OPTION = typer.Option(
    None,
    "--provider-image",
    help="Override the provider base image (e.g. 'ubuntu:22.04').",
)
_MANIFEST_RECOVERY_OPTION = typer.Option(
    None,
    "--manifest",
    help=(
        "Path to a manifest file. Recovery option only — bypasses the active manifest. "
        "Use when the active manifest was lost but the cluster is still running."
    ),
)


def _require_active_manifest() -> str:
    """Return the active manifest path, or exit with a clear error."""
    active = get_active_manifest()
    if active:
        return str(active)
    typer.echo("No active manifest found. Run 'kube-galaxy setup <manifest>' first.")
    raise typer.Exit(code=1)


def _resolve_cleanup_manifest(manifest: str | None) -> str:
    """Resolve manifest for cleanup: explicit option (with warning) or active manifest."""
    if manifest:
        typer.echo(
            f"Warning: using explicit --manifest '{manifest}' instead of the active manifest.\n"
            "This is a recovery option. The active manifest reflects what was actually provisioned."
        )
        return manifest
    active = get_active_manifest()
    if active:
        return str(active)
    typer.echo("No active manifest found. Run 'kube-galaxy setup <manifest>' first.")
    raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def main_callback(
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit"),
) -> None:
    """Kubernetes Galaxy testing infrastructure."""
    if version:
        typer.echo(f"kube-galaxy {__version__}")
        sys.exit(0)


@app.command(name="test")
def test_cmd() -> None:
    """Run tests against the active cluster.

    Examples:
        kube-galaxy test
    """
    test.spread(_require_active_manifest())


@app.command(name="validate")
def validate_cmd(
    manifest: str = typer.Option(
        None, "--manifest", "-m", help="Path to manifest file for validation"
    ),
) -> None:
    """Test and inspect a specific manifest file.

    Examples:
        kube-galaxy validate manifests/baseline-k8s-1.35.yaml
    """
    test.validate(manifest)


@app.command(name="cleanup")
def cleanup_cmd(
    target: str = typer.Argument("all", help="What to cleanup: files, clusters, or all"),
    manifest: str | None = _MANIFEST_RECOVERY_OPTION,
    force: bool = typer.Option(
        False, "--force", "-f", help="Continue cleanup even if errors occur"
    ),
    update_kubeconfig: bool = typer.Option(
        False,
        "--update-kubeconfig",
        help="Remove the 'kube-galaxy' context from ~/.kube/config without prompting",
    ),
) -> None:
    """Clean up temporary files and test clusters.

    Examples:
        kube-galaxy cleanup files
        kube-galaxy cleanup cluster
        kube-galaxy cleanup all --force
        kube-galaxy cleanup all --update-kubeconfig
        kube-galaxy cleanup cluster --manifest manifests/baseline-k8s-1.35.yaml  # recovery only
    """
    match target:
        case "files":
            cleanup.cleanup_files()
        case "cluster":
            cleanup.cleanup_clusters(
                _resolve_cleanup_manifest(manifest), force, update_kubeconfig=update_kubeconfig
            )
        case "all":
            cleanup.cleanup_all(
                _resolve_cleanup_manifest(manifest), force, update_kubeconfig=update_kubeconfig
            )
        case _:
            typer.echo(f"Unknown cleanup target: {target}")
            raise typer.Exit(code=1)


@app.command(name="setup")
def setup_cmd(
    manifest: str = typer.Argument(..., help="Path to manifest file"),
    update_kubeconfig: bool = typer.Option(
        False,
        "--update-kubeconfig",
        help="Merge the 'kube-galaxy' context into ~/.kube/config without prompting",
    ),
    overlays: list[str] = _OVERLAY_OPTION,
    provider_image: str | None = _PROVIDER_IMAGE_OPTION,
) -> None:
    """Provision a cluster from a manifest file.

    Example:
        kube-galaxy setup manifests/baseline-k8s-1.35.yaml
        kube-galaxy setup manifests/baseline-k8s-1.35.yaml --update-kubeconfig
        kube-galaxy setup manifests/baseline-k8s-1.35.yaml --overlay overlays/tweak.yaml
        kube-galaxy setup manifests/baseline-k8s-1.35.yaml --provider-image ubuntu:22.04
    """
    setup.setup(
        manifest,
        update_kubeconfig=update_kubeconfig,
        overlays=overlays or None,
        provider_image=provider_image,
    )


@app.command(name="status")
def status_cmd(
    wait: bool = typer.Option(
        False,
        "--wait",
        help="Wait for cluster nodes and kube-system pods to become Ready",
    ),
    timeout: int = typer.Option(
        300,
        "--timeout",
        min=1,
        help="Readiness wait timeout in seconds (used with --wait)",
    ),
) -> None:
    """Display project status and optional cluster health verification."""
    status.status(_require_active_manifest(), wait=wait, timeout=timeout)


@app.command(name="logs")
def logs_cmd() -> None:
    """Display logs from the most recent test run."""
    logs.logs(_require_active_manifest())


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
