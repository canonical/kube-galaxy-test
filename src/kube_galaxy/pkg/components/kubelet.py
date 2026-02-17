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

    def download_hook(self, arch: str) -> None:
        """
        Downloads the kubelet release binary.
        Constructs download URL from self.config (repo, release, installation).
        """
        if not self.config:
            raise RuntimeError("Component config required for download")

        repo = self.config.repo
        release = self.config.release
        source_format = self.config.installation.source_format

        # Construct download URL from source_format template
        url = source_format.format(repo=repo, release=release, arch=arch)

        # Download to secure temporary directory
        temp_dir = Path(self.component_tmp_dir)
        run(["sudo", "mkdir", "-p", str(temp_dir)], check=True)

        binary_path = temp_dir / "kubelet"
        download_file(url, binary_path)

        # Store download location as instance attribute
        self.binary_path = binary_path

    def install_hook(self, arch: str) -> None:
        """
        Install kubelet binary to system.

        Requires download_hook to have completed first.
        """
        if not hasattr(self, "binary_path") or not self.binary_path.exists():
            raise RuntimeError("kubelet binary not downloaded. Run download hook first.")

        # Install binary to system
        self.install_path = install_binary(self.binary_path, "kubelet", self.COMPONENT_NAME)

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
        temp_service = Path(self.component_tmp_dir) / "kubelet.service"
        service_content = service_content.replace("/usr/bin/kubelet", self.install_path)
        run(["sudo", "mkdir", "-p", str(temp_service.parent)], check=True)
        run(["sudo", "tee", str(temp_service)], input=service_content, text=True, check=True)
        run(["sudo", "mkdir", "-p", "/usr/lib/systemd/system"], check=True)
        run(
            ["sudo", "cp", str(temp_service), "/usr/lib/systemd/system/kubelet.service"], check=True
        )

    def bootstrap_hook(self) -> None:
        """
        Starts kubelet service and enables it to start on boot.
        """
        run(["sudo", "systemctl", "daemon-reload"], check=True)
        run(["sudo", "systemctl", "enable", "--now", "kubelet"], check=True)

    def verify_hook(self) -> None:
        """Verify kubelet is working correctly."""
        # Check kubelet systemctl status
        run(["systemctl", "is-active", "kubelet"], check=True)

    def stop_hook(self) -> None:
        """Stop the kubelet service."""
        from kube_galaxy.pkg.utils.logging import info

        try:
            run(["sudo", "systemctl", "stop", "kubelet"], check=False)
            info("Stopped kubelet service")
        except Exception as e:
            info(f"Failed to stop kubelet service: {e}")

    def delete_hook(self) -> None:
        """Remove kubelet binary and configuration."""
        from kube_galaxy.pkg.utils.logging import info

        # Remove kubelet binary
        if self.install_path and Path(self.install_path).exists():
            Path(self.install_path).unlink()
            info(f"Removed kubelet binary: {self.install_path}")

    def post_delete_hook(self) -> None:
        """Clean up kubelet data directory and remaining files."""
        from kube_galaxy.pkg.utils.logging import info

        # Remove kubelet data directory
        kubelet_dir = Path("/var/lib/kubelet")
        if kubelet_dir.exists():
            try:
                run(["sudo", "rm", "-rf", str(kubelet_dir)], check=False)
                info(f"Removed kubelet directory: {kubelet_dir}")
            except Exception as e:
                info(f"Failed to remove {kubelet_dir}: {e}")
