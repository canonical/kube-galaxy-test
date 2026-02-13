"""CLI output formatting and logging."""

from typing import Any

import typer


def info(message: str) -> None:
    """Print info message."""
    typer.echo(message)


def success(message: str) -> None:
    """Print success message with checkmark."""
    typer.echo(typer.style(f"✅ {message}", fg=typer.colors.GREEN))


def error(message: str) -> None:
    """Print error message with X mark."""
    typer.echo(typer.style(f"❌ {message}", fg=typer.colors.RED))


def warning(message: str) -> None:
    """Print warning message."""
    typer.echo(typer.style(f"⚠️  {message}", fg=typer.colors.YELLOW))


def section(title: str) -> None:
    """Print section header."""
    typer.echo("")
    typer.echo(typer.style(title, fg=typer.colors.CYAN, bold=True))
    typer.echo("=" * len(title))
    typer.echo("")


def print_dict(data: dict[str, Any], indent: int = 2) -> None:
    """Pretty print dictionary."""
    for key, value in data.items():
        typer.echo(f"{' ' * indent}{key}: {value}")
