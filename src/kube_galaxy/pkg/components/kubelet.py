"""
Kubelet component installation and management.

Kubelet is the primary node agent running on each node.
"""

import requests

from kube_galaxy.pkg.components import ComponentBase, register_component
from kube_galaxy.pkg.literals import URLs
from kube_galaxy.pkg.utils.logging import info


@register_component("kubelet")
class Kubelet(ComponentBase):
    """
    Kubelet component for Kubernetes nodes.

    This component handles kubelet installation and configuration.
    """

    def _system_settings(self) -> None:
        """
        Apply necessary system settings for kubelet.
        """
        # Disable swap which is required for kubelet to work properly
        info("    Disabling swap...")
        self.unit.run(["swapoff", "-a"], privileged=True)

    def configure_hook(self) -> None:
        """
        Configures kubelet systemd service to be ready to start by kubeadm.

        Configure the kubelet.service based on the Kubernetes release repository,
        replaces /usr/bin with the actual kubelet installation path, and creates
        the systemd service file and service.d directory.
        """
        self._system_settings()

        # Download kubelet.service from Kubernetes release repository
        service_url = f"{URLs.K8S_RELEASE_BASE}/cmd/krel/templates/latest/kubelet/kubelet.service"
        resp = requests.get(service_url, timeout=30)
        resp.raise_for_status()
        service_content = resp.text
        install_path = self.install_path or "/usr/local/bin/kubelet"
        service_content = service_content.replace("/usr/bin/kubelet", install_path)

        self.create_systemd_service("kubelet", service_content)

    def bootstrap_hook(self) -> None:
        """
        Starts kubelet service and enables it to start on boot.
        """
        self.unit.run(["systemctl", "daemon-reload"], privileged=True)
        self.unit.run(["systemctl", "enable", "--now", "kubelet"], privileged=True)

    def verify_hook(self) -> None:
        """Verify kubelet is working correctly."""
        # Check kubelet systemctl status
        self.unit.run(["systemctl", "is-active", "kubelet"], privileged=True)

    def stop_hook(self) -> None:
        """Stop the kubelet service."""
        try:
            self.unit.run(["systemctl", "stop", "kubelet"], privileged=True, check=False)
            info("Stopped kubelet service")
        except Exception as e:
            info(f"Failed to stop kubelet service: {e}")

    def post_delete_hook(self) -> None:
        """Clean up kubelet data directory and remaining files."""
        # Remove kubelet data directory
        self.remove_directories(["/var/lib/kubelet"])
