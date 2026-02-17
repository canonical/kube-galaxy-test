"""
Kubectl component installation and management.

Kubectl is the command-line tool for communicating with Kubernetes clusters.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class Kubectl(ComponentBase):
    """
    Kubectl component for cluster interaction.

    This component handles kubectl installation for cluster management.
    """

    # Component metadata
    COMPONENT_NAME = "kubectl"
    CATEGORY = "kubernetes/kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 100

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes

    def download_hook(self, arch: str) -> None:
        """
        Download kubectl binary using base method.
        """
        # Use base method for standard binary download
        self.binary_path = self.download_binary_from_config(arch, "kubectl")

    def install_hook(self, arch: str) -> None:
        """
        Install kubectl binary using base install method.
        """
        if not hasattr(self, "binary_path") or not self.binary_path.exists():
            raise RuntimeError("kubectl binary not downloaded. Run download hook first.")

        # Use base method for standard binary installation
        self.install_path = self.install_downloaded_binary(self.binary_path)
