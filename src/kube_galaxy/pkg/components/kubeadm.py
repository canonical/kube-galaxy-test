"""
Kubeadm component installation and management.

Kubeadm is used to bootstrap Kubernetes clusters.
"""

from pathlib import Path

from kube_galaxy.pkg.utils.components import (
    download_file,
    install_binary,
    remove_binary,
)


def install(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install kubeadm binary.

    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v1.33.4')
        format: Installation format (Binary)
        arch: Architecture (amd64, arm64, etc.)
    """
    # Ensure version has 'v' prefix
    if not release.startswith("v"):
        release = f"v{release}"

    # Construct download URL
    filename = "kubeadm"
    url = f"{repo}/releases/download/{release}/bin/linux/{arch}/{filename}"

    # Download binary
    temp_dir = Path("/tmp/kubeadm-install")
    temp_dir.mkdir(parents=True, exist_ok=True)

    binary_path = temp_dir / "kubeadm"
    download_file(url, binary_path)

    # Install binary
    install_binary(binary_path, "kubeadm")


def configure() -> None:
    """
    Configure kubeadm.

    Kubeadm configuration is typically handled during cluster bootstrap.
    """
    pass


def remove() -> None:
    """
    Remove kubeadm.

    Removes binary.
    """
    remove_binary("kubeadm")
