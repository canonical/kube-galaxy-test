"""
Runc component installation and management.

Runc is the container runtime specification implementation used by containerd.
"""

from pathlib import Path

from kube_galaxy.pkg.utils.components import (
    download_file,
    install_binary,
    remove_binary,
)


def install(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install runc binary.

    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v1.3.0')
        format: Installation format (Binary)
        arch: Architecture (amd64, arm64, etc.)
    """
    # Ensure version has 'v' prefix
    if not release.startswith("v"):
        release = f"v{release}"

    # Construct download URL
    filename = f"runc.{arch}"
    url = f"{repo}/releases/download/{release}/{filename}"

    # Download binary
    temp_dir = Path("/tmp/runc-install")
    temp_dir.mkdir(parents=True, exist_ok=True)

    binary_path = temp_dir / "runc"
    download_file(url, binary_path)

    # Install binary
    install_binary(binary_path, "runc")


def configure() -> None:
    """
    Configure runc.

    Runc is primarily used as a library by containerd, so minimal configuration needed.
    """
    pass


def remove() -> None:
    """
    Remove runc.

    Removes binary.
    """
    remove_binary("runc")
