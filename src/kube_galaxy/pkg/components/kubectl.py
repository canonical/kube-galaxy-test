"""
Kubectl component installation and management.

Kubectl is the command-line tool for communicating with Kubernetes clusters.
"""

from pathlib import Path

from kube_galaxy.pkg.utils.components import (
    download_file,
    install_binary,
    remove_binary,
)


def install(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install kubectl binary.

    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v1.33.4')
        format: Installation format (Binary+Container)
        arch: Architecture (amd64, arm64, etc.)
    """
    # Ensure version has 'v' prefix
    if not release.startswith("v"):
        release = f"v{release}"

    # Construct download URL
    filename = "kubectl"
    url = f"{repo}/releases/download/{release}/bin/linux/{arch}/{filename}"

    # Download binary
    temp_dir = Path("/tmp/kubectl-install")
    temp_dir.mkdir(parents=True, exist_ok=True)

    binary_path = temp_dir / "kubectl"
    download_file(url, binary_path)

    # Install binary
    install_binary(binary_path, "kubectl")


def configure() -> None:
    """
    Configure kubectl.

    Kubectl configuration is handled by end users typically.
    """
    pass


def remove() -> None:
    """
    Remove kubectl.

    Removes binary.
    """
    remove_binary("kubectl")
