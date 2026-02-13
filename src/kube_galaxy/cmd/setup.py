"""Setup command handler."""

from pathlib import Path

from kube_galaxy.pkg.utils.logging import info, section, success


def setup() -> None:
    """Initial project setup - create necessary directories."""
    section("Setting Up Project")

    directories = [
        "test-results",
        "spread-results",
        "debug-logs",
        "cleanup-logs",
    ]

    for dir_name in directories:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            info(f"Created directory: {dir_name}")
        else:
            info(f"Directory already exists: {dir_name}")

    success("Project setup completed!")
