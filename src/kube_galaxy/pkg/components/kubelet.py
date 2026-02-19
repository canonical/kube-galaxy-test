"""
Kubelet component installation and management.

Kubelet is the primary node agent running on each node.
"""

from typing import ClassVar
from urllib.request import urlopen

from kube_galaxy.pkg.components import ComponentBase, register_component
from kube_galaxy.pkg.literals import Commands, URLs
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.shell import run


@register_component
class Kubelet(ComponentBase):
    """
    Kubelet component for Kubernetes nodes.

    This component handles kubelet installation and configuration.
    """

    # Component metadata
    CATEGORY = "kubernetes/kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = ["containerd"]

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 180  # 3 minutes
    INSTALL_TIMEOUT = 120  # 2 minutes
    CONFIGURE_TIMEOUT = 120  # 2 minutes
    VERIFY_TIMEOUT = 120  # 2 minutes

    def _system_settings(self) -> None:
        """
        Apply necessary system settings for kubelet.
        """
        # Disable swap which is required for kubelet to work properly
        info("    Disabling swap...")
        run(["sudo", "swapoff", "-a"], check=True)

    def configure_hook(self, arch: str) -> None:
        """
        Configures kubelet systemd service to be ready to start by kubeadm.

        Configure the kubelet.service based on the Kubernetes release repository,
        replaces /usr/bin with the actual kubelet installation path, and creates
        the systemd service file and service.d directory.
        """
        self._system_settings()

        # Download kubelet.service from Kubernetes release repository
        service_url = f"{URLs.K8S_RELEASE_BASE}/cmd/krel/templates/latest/kubelet/kubelet.service"
        with urlopen(service_url) as response:
            service_content = response.read().decode("utf-8")
        service_content = service_content.replace("/usr/bin/kubelet", self.install_path)

        self.create_systemd_service("kubelet", service_content)

    def bootstrap_hook(self) -> None:
        """
        Starts kubelet service and enables it to start on boot.
        """
        run(Commands.SYSTEMCTL_DAEMON_RELOAD, check=True)
        run([*Commands.SYSTEMCTL_ENABLE, "--now", "kubelet"], check=True)

    def verify_hook(self) -> None:
        """Verify kubelet is working correctly."""
        # Check kubelet systemctl status
        run([*Commands.SYSTEMCTL_IS_ACTIVE, "kubelet"], check=True)

    def stop_hook(self) -> None:
        """Stop the kubelet service."""
        try:
            run([*Commands.SYSTEMCTL_STOP, "kubelet"], check=False)
            info("Stopped kubelet service")
        except Exception as e:
            info(f"Failed to stop kubelet service: {e}")

    def delete_hook(self) -> None:
        """Remove kubelet binary and configuration."""
        # Remove kubelet binary
        self.remove_installed_binary()

    def post_delete_hook(self) -> None:
        """Clean up kubelet data directory and remaining files."""
        # Remove kubelet data directory
        self.remove_directories(["/var/lib/kubelet"])
