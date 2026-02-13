"""
Kubelet component installation and management.

Kubelet is the primary node agent running on each node.
"""

from pathlib import Path
from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.utils.components import download_file
from kube_galaxy.pkg.utils.errors import ComponentError


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
        Download kubelet binary.

        Downloads the kubelet release binary.
        """
        if not self.config:
            raise ComponentError("Component config required for download")

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
