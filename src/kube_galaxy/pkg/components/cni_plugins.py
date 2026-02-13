"""
CNI Plugins component installation and management.

CNI (Container Network Interface) plugins provide networking for Kubernetes.
"""

from pathlib import Path

from kube_galaxy.pkg.utils.components import (
    download_file,
    extract_archive,
)


def install(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install CNI plugins.

    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v1.6.2')
        format: Installation format (Container)
        arch: Architecture (amd64, arm64, etc.)
    """
    # Ensure version has 'v' prefix
    if not release.startswith("v"):
        release = f"v{release}"

    # Construct download URL
    filename = f"cni-plugins-linux-{arch}-{release}.tgz"
    url = f"{repo}/releases/download/{release}/{filename}"

    # Download to temporary directory
    temp_dir = Path("/tmp/cni-plugins-install")
    temp_dir.mkdir(parents=True, exist_ok=True)

    archive_path = temp_dir / filename
    download_file(url, archive_path)

    # Extract archive
    extract_dir = temp_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)
    extract_archive(archive_path, extract_dir)

    # Install CNI plugins to standard location
    cni_bin_dir = Path("/opt/cni/bin")
    cni_bin_dir.mkdir(parents=True, exist_ok=True)

    # Copy all binaries
    for binary in extract_dir.glob("*"):
        if binary.is_file() and binary.name != "*.md":
            import shutil

            shutil.copy2(binary, cni_bin_dir / binary.name)
            (cni_bin_dir / binary.name).chmod(0o755)


def configure() -> None:
    """
    Configure CNI plugins.

    Create network configuration directory.
    """
    net_conf_dir = Path("/etc/cni/net.d")
    net_conf_dir.mkdir(parents=True, exist_ok=True)


def remove() -> None:
    """
    Remove CNI plugins.

    Removes plugin binaries.
    """
    cni_bin_dir = Path("/opt/cni/bin")
    if cni_bin_dir.exists():
        import shutil

        shutil.rmtree(cni_bin_dir, ignore_errors=True)
