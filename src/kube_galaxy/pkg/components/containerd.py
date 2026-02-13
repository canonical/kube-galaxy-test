"""
Containerd component installation and management.

Containerd is the container runtime used by Kubernetes clusters.
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
    Install containerd binary.

    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v2.0.6')
        format: Installation format (Binary, Binary+Container)
        arch: Architecture (amd64, arm64, etc.)
    """
    # Ensure version has 'v' prefix
    if not release.startswith("v"):
        release = f"v{release}"

    # Construct download URL
    filename = f"containerd-{release}.linux-{arch}.tar.gz"
    url = f"{repo}/releases/download/{release}/{filename}"

    # Download to temporary directory
    temp_dir = Path("/tmp/containerd-install")
    temp_dir.mkdir(parents=True, exist_ok=True)

    archive_path = temp_dir / filename
    download_file(url, archive_path)

    # Extract archive
    extract_dir = temp_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)
    extract_archive(archive_path, extract_dir)

    # Install binary
    binary_path = extract_dir / "bin" / "containerd"
    if not binary_path.exists():
        raise ComponentError(f"containerd binary not found in archive at {binary_path}")

    install_binary(binary_path, "containerd")


def configure() -> None:
    """
    Configure containerd.

    Creates systemd service unit and default configuration.
    """
    # Create systemd service unit
    systemd_unit = """[Unit]
Description=containerd container runtime
Documentation=https://containerd.io
After=network.target local-fs.target

[Service]
ExecStart=/usr/local/bin/containerd
ExecStop=/bin/kill -s TERM $MAINPID
Restart=on-failure
RestartSec=5
Delegate=yes
KillMode=process
OOMScoreAdjust=-999
LimitNOFILE=1048576
LimitNPROC=infinity

[Install]
WantedBy=multi-user.target
"""

    unit_path = Path("/etc/systemd/system/containerd.service")
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(systemd_unit)

    # Reload systemd and enable service
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "containerd"])
    run(["systemctl", "start", "containerd"])


def remove() -> None:
    """
    Remove containerd.

    Stops service and removes binary.
    """
    try:
        run(["systemctl", "stop", "containerd"], check=False)
        run(["systemctl", "disable", "containerd"], check=False)
    except Exception:
        pass

    remove_binary("containerd")

    # Remove systemd unit
    unit_path = Path("/etc/systemd/system/containerd.service")
    if unit_path.exists():
        unit_path.unlink()

    run(["systemctl", "daemon-reload"], check=False)
