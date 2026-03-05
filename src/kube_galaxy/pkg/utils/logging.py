"""CLI output formatting and logging."""

import traceback
from typing import Any

import typer


def info(message: str) -> None:
    """Print info message."""
    typer.echo(message)


def success(message: str) -> None:
    """Print success message with checkmark."""
    typer.echo(typer.style(f"✅ {message}", fg=typer.colors.GREEN))


def error(message: str, exc: Exception | None = None, show_traceback: bool = True) -> None:
    """
    Print error message with X mark.

    Args:
        message: Error message to display
        exc: Optional exception to extract traceback from
        show_traceback: Whether to show full traceback (default: True)
    """
    typer.echo(typer.style(f"❌ {message}", fg=typer.colors.RED), err=True)

    # Show exception details if provided
    if exc and show_traceback:
        typer.echo(typer.style("\nError Details:", fg=typer.colors.RED, bold=True), err=True)
        typer.echo(typer.style(f"  Type: {type(exc).__name__}", fg=typer.colors.RED), err=True)
        typer.echo(typer.style(f"  Message: {exc!s}", fg=typer.colors.RED), err=True)

        # Show full traceback
        typer.echo(typer.style("\nStack Trace:", fg=typer.colors.RED, bold=True), err=True)
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        for line in tb_lines:
            typer.echo(typer.style(line.rstrip(), fg=typer.colors.RED), err=True)


def exception(message: str, exc: Exception) -> None:
    """
    Print error message with full exception traceback.

    This is a convenience function that always shows the traceback.

    Args:
        message: Context message describing what failed
        exc: The exception that was raised
    """
    error(message, exc=exc, show_traceback=True)


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
