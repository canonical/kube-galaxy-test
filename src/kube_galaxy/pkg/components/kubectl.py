"""
Kubectl component installation and management.

Kubectl is the command-line tool for communicating with Kubernetes clusters.
"""

from pathlib import Path
from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.utils.components import download_file
from kube_galaxy.pkg.utils.errors import ComponentError


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
        Download kubectl binary.

        Constructs download URL from self.config (repo, release, installation).
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        repo = self.config.repo
        release = self.config.release
        source_format = self.config.installation.source_format

        # Construct download URL from source_format template
        url = source_format.format(repo=repo, release=release, arch=arch)

        # Download to temporary directory
        temp_dir = Path("/tmp/kubectl-install")
        temp_dir.mkdir(parents=True, exist_ok=True)

        binary_path = temp_dir / "kubectl"
        download_file(url, binary_path)

        # Store download location as instance attribute
        self.binary_path = binary_path
