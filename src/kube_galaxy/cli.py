"""Main CLI entry point for kube-galaxy."""

import sys

import typer

from kube_galaxy import __version__
from kube_galaxy.cmd import cleanup, setup, status, test

app = typer.Typer(
    help="Kubernetes Galaxy: Scalable Kubernetes testing infrastructure",
    invoke_without_command=False,
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main_callback(
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit"),
) -> None:
    """Kubernetes Galaxy testing infrastructure."""
    if version:
        typer.echo(f"kube-galaxy {__version__}")
        sys.exit(0)


@app.command(name="test")
def test_cmd(
    manifest: str = typer.Argument(..., help="Path to manifest file"),
) -> None:
    """Run tests or manage test clusters.

    Examples:
        kube-galaxy test manifests/baseline-k8s-1.35.yaml
    """
    test.spread(manifest)


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
    manifest: str = typer.Option(
        None, "--manifest", "-m", help="Path to manifest file for cluster cleanup"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Continue cleanup even if errors occur"
    ),
) -> None:
    """Clean up temporary files and test clusters.

    Examples:
        kube-galaxy cleanup files
        kube-galaxy cleanup clusters --manifest manifests/baseline-k8s-1.35.yaml
        kube-galaxy cleanup all --manifest manifests/baseline-k8s-1.35.yaml --force
    """
    match target:
        case "files":
            cleanup.cleanup_files()
        case "clusters":
            cleanup.cleanup_clusters(manifest, force)
        case "all":
            cleanup.cleanup_all(manifest, force)
        case _:
            typer.echo(f"Unknown cleanup target: {target}")
            raise typer.Exit(code=1)


@app.command(name="setup")
def setup_cmd(
    manifest: str = typer.Argument(..., help="Path to manifest file"),
) -> None:
    """Provision a cluster from a manifest file.

    Example:
        kube-galaxy setup manifests/baseline-k8s-1.35.yaml
    """
    setup.setup(manifest)


@app.command(name="status")
def status_cmd() -> None:
    """Display project status and dependency information."""
    status.status()


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
