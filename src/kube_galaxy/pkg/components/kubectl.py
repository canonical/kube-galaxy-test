"""
Kubectl component installation and management.

Kubectl is the command-line tool for communicating with Kubernetes clusters.
"""

from pathlib import Path
from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.utils.components import (
    download_file,
    install_binary,
)
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.shell import run


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

        # Download to secure temporary directory
        temp_dir = Path(self.component_tmp_dir)
        run(["sudo", "mkdir", "-p", str(temp_dir)], check=True)

        binary_path = temp_dir / "kubectl"
        download_file(url, binary_path)

        # Store download location as instance attribute
        self.binary_path = binary_path

    def install_hook(self, arch: str) -> None:
        """
        Install kubectl binary to system.

        Requires download_hook to have completed first.
        """
        if not hasattr(self, "binary_path") or not self.binary_path.exists():
            raise RuntimeError("kubectl binary not downloaded. Run download hook first.")

        # Install binary to system
        self.install_path = install_binary(self.binary_path, "kubectl", self.COMPONENT_NAME)
