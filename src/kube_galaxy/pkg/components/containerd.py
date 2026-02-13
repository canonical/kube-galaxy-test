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

    def download_hook(self, arch: str) -> None:
        """
        Download containerd binary archive.

        Constructs download URL from self.config (repo, release, installation).
        Extracts archive for install hook.
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        repo = self.config.repo
        release = self.config.release
        source_format = self.config.installation.source_format

        # Construct download URL from source_format template
        url = source_format.format(repo=repo, release=release, arch=arch)
        filename = url.split("/")[-1]

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

    def install_hook(self, arch: str) -> None:
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

    def verify_hook(self) -> None:
        """
        Verify containerd is running and functional.

        Checks service status and command availability.
        """
        # Check service is active
        run(["systemctl", "is-active", "containerd"], check=True)

        # Check containerd command works
        run(["containerd", "--version"], check=True)
