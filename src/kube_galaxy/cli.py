"""Main CLI entry point for kube-galaxy."""

import sys

import typer

from kube_galaxy import __version__
from kube_galaxy.cmd import cleanup, setup, status, test, validate

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


@app.command(name="validate")
def validate_cmd(
    target: str = typer.Argument(
        "all",
        help="What to validate: manifests, workflows, actions, or all",
    ),
) -> None:
    """Validate cluster manifests, workflows, and actions.

    Examples:
        kube-galaxy validate all
        kube-galaxy validate manifests
    """
    match target:
        case "manifests":
            validate.validate_manifests_cmd()
        case "all":
            validate.validate_all()
        case _:
            typer.echo(f"Unknown validation target: {target}")
            raise typer.Exit(code=1)


@app.command(name="test")
def test_cmd(
    target: str = typer.Argument("local", help="What to test: local, spread, or setup"),
) -> None:
    """Run tests or manage test clusters.

    Examples:
        kube-galaxy test local
        kube-galaxy test spread
        kube-galaxy test setup
    """
    match target:
        case "local":
            test.local()
        case "spread":
            test.spread()
        case "setup":
            test.setup()
        case _:
            typer.echo(f"Unknown test target: {target}")
            raise typer.Exit(code=1)


@app.command(name="test-manifest")
def test_manifest_cmd(
    manifest: str = typer.Argument(..., help="Path to manifest file"),
) -> None:
    """Test and inspect a specific manifest file.

    Examples:
        kube-galaxy test-manifest manifests/baseline-k8s-1.35.yaml
    """
    test.manifest(manifest)


@app.command(name="cleanup")
def cleanup_cmd(
    target: str = typer.Argument("all", help="What to cleanup: files, clusters, or all"),
) -> None:
    """Clean up temporary files and test clusters.

    Examples:
        kube-galaxy cleanup files
        kube-galaxy cleanup clusters
        kube-galaxy cleanup all
    """
    match target:
        case "files":
            cleanup.cleanup_files()
        case "clusters":
            cleanup.cleanup_clusters()
        case "all":
            cleanup.cleanup_all()
        case _:
            typer.echo(f"Unknown cleanup target: {target}")
            raise typer.Exit(code=1)


@app.command(name="setup")
def setup_cmd() -> None:
    """Initialize project setup - create necessary directories."""
    setup.setup()


@app.command(name="status")
def status_cmd() -> None:
    """Display project status and dependency information."""
    status.status()


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
