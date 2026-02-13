"""
Etcdctl component installation and management.

Etcdctl is the command-line client for etcd.
"""

from pathlib import Path

from kube_galaxy.pkg.utils.components import (
    download_file,
    extract_archive,
    install_binary,
    remove_binary,
)
from kube_galaxy.pkg.utils.errors import ComponentError


def install(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install etcdctl binary.

    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v3.5.22')
        format: Installation format (Binary+Container)
        arch: Architecture (amd64, arm64, etc.)
    """
    # Ensure version has 'v' prefix
    if not release.startswith("v"):
        release = f"v{release}"

    # Construct download URL
    filename = f"etcd-{release}-linux-{arch}.tar.gz"
    url = f"{repo}/releases/download/{release}/{filename}"

    # Download to temporary directory
    temp_dir = Path("/tmp/etcdctl-install")
    temp_dir.mkdir(parents=True, exist_ok=True)

    archive_path = temp_dir / filename
    download_file(url, archive_path)

    # Extract archive
    extract_dir = temp_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)
    extract_archive(archive_path, extract_dir)

    # Find and install etcdctl binary
    # Archive contains etcd-vX.Y.Z-linux-arch/etcdctl
    import glob

    etcdctl_paths = list(glob.glob(str(extract_dir / "*" / "etcdctl")))
    if not etcdctl_paths:
        raise ComponentError("etcdctl binary not found in archive")

    binary_path = Path(etcdctl_paths[0])
    install_binary(binary_path, "etcdctl")


def configure() -> None:
    """
    Configure etcdctl.

    Etcdctl is primarily used as a client tool, minimal configuration needed.
    """
    pass


def remove() -> None:
    """
    Remove etcdctl.

    Removes binary.
    """
    remove_binary("etcdctl")
