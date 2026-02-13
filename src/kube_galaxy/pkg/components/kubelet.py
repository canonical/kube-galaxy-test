"""
Kubelet component installation and management.

Kubelet is the primary node agent running on each node.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


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

    def download_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        """
        Download kubelet binary.

        Downloads the kubelet release binary.
        """
        pass

    def install_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        """
        Install kubelet binary.

        Installs kubelet to system.
        """
        pass

    def configure_hook(self) -> None:
        """
        Configure kubelet.

        Creates systemd service unit for kubelet.
        """
        pass

    def remove_hook(self) -> None:
        """
        Remove kubelet.

        Stops service and removes binary.
        """
        pass

    def verify_hook(self) -> None:
        """
        Verify kubelet is running.

        Checks that kubelet service is accessible.
        """
        pass
