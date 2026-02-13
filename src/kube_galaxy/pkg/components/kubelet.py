"""
Kubelet component installation and management.

Kubelet is the primary node agent running on each node.
"""

from pathlib import Path
from typing import ClassVar
from urllib.request import urlopen

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.utils.components import (
    download_file,
    install_binary,
)
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.shell import run


class Kubelet(ComponentBase):
    """
    Kubelet component for Kubernetes nodes.

    This component handles kubelet installation and configuration.
    """

    # Component metadata
    COMPONENT_NAME = "kubelet"
    CATEGORY = "kubernetes/kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = ["containerd"]
    PRIORITY = 50

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 180  # 3 minutes
    INSTALL_TIMEOUT = 120  # 2 minutes
    CONFIGURE_TIMEOUT = 120  # 2 minutes
    VERIFY_TIMEOUT = 120  # 2 minutes
    INSTALL_PATH = "/usr/local/bin/kubelet"

    def download_hook(self, arch: str) -> None:
        """
        Downloads the kubelet release binary.
        """
        repo = self.config.repo
        release = self.config.release
        source_format = self.config.installation.source_format

        # Construct download URL from source_format template
        url = source_format.format(repo=repo, release=release, arch=arch)

        # Download to temporary directory
        temp_dir = Path("/tmp/kubelet-install")
        temp_dir.mkdir(parents=True, exist_ok=True)

        binary_path = temp_dir / "kubelet"
        download_file(url, binary_path)

        # Store download location as instance attribute
        self.binary_path = binary_path

    def install_hook(self, arch: str) -> None:
        """
        Installs kubelet binary to /usr/local/bin/kubelet.
        """
        if not hasattr(self, "binary_path"):
            raise ComponentError("Binary path not set. Download must be completed before install.")

        install_binary(self.binary_path, self.INSTALL_PATH)

    def configure_hook(self) -> None:
        """
        Configures kubelet systemd service to be ready to start by kubeadm.

        Downloads the kubelet.service template from the Kubernetes release repository,
        replaces /usr/bin with the actual kubelet installation path, and creates
        the systemd service file and service.d directory.
        """
        if not self.config:
            raise ComponentError("Config required for configuration")

        # Download kubelet.service from Kubernetes release repository
        service_url = "https://raw.githubusercontent.com/kubernetes/release/v0.16.2/cmd/krel/templates/latest/kubelet/kubelet.service"
        with urlopen(service_url) as response:
            service_content = response.read().decode("utf-8")

        # Create systemd directories
        run(["sudo", "mkdir", "-p", "/usr/lib/systemd/system/kubelet.service.d"], check=True)

        # Write kubelet.service file
        temp_service = Path("/tmp/kubelet.service")
        service_content = service_content.replace("/usr/bin/kubelet", self.INSTALL_PATH)
        temp_service.write_text(service_content)
        run(["sudo", "mkdir", "-p", "/usr/lib/systemd/system"], check=True)
        run(["sudo", "cp", str(temp_service), "/usr/lib/systemd/system/kubelet.service"], check=True)

    def bootstrap_hook(self) -> None:
        """
        Starts kubelet service and enables it to start on boot.
        """
        run(["sudo", "systemctl", "daemon-reload"], check=True)
        run(["sudo", "systemctl", "enable", "--now", "kubelet"], check=True)
