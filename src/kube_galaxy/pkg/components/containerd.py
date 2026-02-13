"""
Containerd component installation and management.

Containerd is the container runtime used by Kubernetes clusters.
"""

from pathlib import Path
from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.utils.components import (
    download_file,
    extract_archive,
    install_binary,
)
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.shell import run


class Containerd(ComponentBase):
    """
    Containerd container runtime component.

    Handles downloading, installing, and starting the containerd
    container runtime for Kubernetes.
    """

    # Component metadata
    COMPONENT_NAME = "containerd"
    CATEGORY = "containerd"
    DEPENDENCIES: ClassVar[list[str]] = ["runc"]
    PRIORITY = 10

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 300  # 5 minutes (containerd archive can be large)
    INSTALL_TIMEOUT = 120  # 2 minutes (extract and copy)
    BOOTSTRAP_TIMEOUT = 60  # 1 minute (start service)
    CONFIGURE_TIMEOUT = 60  # 1 minute (verify service running)

    def download_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        """
        Download containerd binary archive.

        Checks for custom_binary_url first, otherwise constructs from repo/release.
        Extracts archive for install hook.
        """
        # Check for custom URL using property
        url = self.custom_binary_url

        if url:
            # Extract filename from URL for archive format detection
            filename = url.split("/")[-1]
        else:
            # Ensure version has 'v' prefix
            if not release.startswith("v"):
                release = f"v{release}"

            # Get archive format from component config using property
            archive_fmt = self.archive_format or "tar.gz"

            # Construct download URL
            filename = f"containerd-{release}.linux-{arch}.{archive_fmt}"
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

        # Store paths as instance attribute
        self.extract_dir = extract_dir

    def install_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        """
        Install containerd binary from extracted archive.

        Requires download_hook to have completed first.
        """
        if not hasattr(self, "extract_dir") or not self.extract_dir.exists():
            raise ComponentError("containerd archive not downloaded. Run download hook first.")

        # Install binary
        binary_path = self.extract_dir / "bin" / "containerd"
        if not binary_path.exists():
            raise ComponentError(f"containerd binary not found in archive at {binary_path}")

        install_binary(binary_path, "containerd")

    def configure_hook(self) -> None:
        """
        Configure containerd with systemd service.

        Creates systemd service unit and enables it.
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

    def bootstrap_hook(self) -> None:
        """
        Start containerd service.
        """
        run(["systemctl", "start", "containerd"])
