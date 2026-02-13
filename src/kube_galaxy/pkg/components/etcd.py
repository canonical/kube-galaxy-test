"""
Etcd component installation and management.

Etcd is the key-value store backing Kubernetes.
"""

from pathlib import Path

from kube_galaxy.pkg.utils.components import (
    download_file,
    extract_archive,
    install_binary,
    remove_binary,
)
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.shell import run


def install(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install etcd.

    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v3.5.22')
        format: Installation format (Container)
        arch: Architecture (amd64, arm64, etc.)
    """
    # Ensure version has 'v' prefix
    if not release.startswith("v"):
        release = f"v{release}"

    # Construct download URL
    filename = f"etcd-{release}-linux-{arch}.tar.gz"
    url = f"{repo}/releases/download/{release}/{filename}"

    # Download to temporary directory
    temp_dir = Path("/tmp/etcd-install")
    temp_dir.mkdir(parents=True, exist_ok=True)

    archive_path = temp_dir / filename
    download_file(url, archive_path)

    # Extract archive
    extract_dir = temp_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)
    extract_archive(archive_path, extract_dir)

    # Find and install etcd binary
    import glob

    etcd_paths = list(glob.glob(str(extract_dir / "*" / "etcd")))
    if not etcd_paths:
        raise ComponentError("etcd binary not found in archive")

    binary_path = Path(etcd_paths[0])
    install_binary(binary_path, "etcd")


def configure() -> None:
    """
    Configure etcd.

    Creates systemd service unit for etcd.
    """
    systemd_unit = """[Unit]
Description=etcd
Documentation=https://etcd.io/docs
After=network.target

[Service]
ExecStart=/usr/local/bin/etcd \\
  --name=etcd \\
  --listen-client-urls=http://127.0.0.1:2379 \\
  --advertise-client-urls=http://127.0.0.1:2379 \\
  --listen-peer-urls=http://127.0.0.1:2380
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

    unit_path = Path("/etc/systemd/system/etcd.service")
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(systemd_unit)

    # Reload systemd
    run(["systemctl", "daemon-reload"], check=False)


def remove() -> None:
    """
    Remove etcd.

    Stops service and removes binary.
    """
    try:
        run(["systemctl", "stop", "etcd"], check=False)
        run(["systemctl", "disable", "etcd"], check=False)
    except Exception:
        pass

    remove_binary("etcd")

    # Remove systemd unit
    unit_path = Path("/etc/systemd/system/etcd.service")
    if unit_path.exists():
        unit_path.unlink()

    run(["systemctl", "daemon-reload"], check=False)
