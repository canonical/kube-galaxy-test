"""
Runc component installation and management.

Runc is the container runtime specification implementation used by containerd.
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


class Runc(ComponentBase):
    """
    Runc component for container runtime.

    This component handles runc installation for containerd integration.
    """

    # Component metadata
    COMPONENT_NAME = "runc"
    CATEGORY = "containerd"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 100

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes

    def download_hook(self, arch: str) -> None:
        """
        Download runc binary archive.

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

        # Download to secure temporary directory
        temp_dir = Path(self.component_tmp_dir)
        run(["sudo", "mkdir", "-p", str(temp_dir)], check=True)

        binary_path = temp_dir / filename
        download_file(url, binary_path)

        # Store paths as instance attribute
        self.binary_path = binary_path

    def install_hook(self, arch: str) -> None:
        """
        Install runc binary to system.

        Requires download_hook to have completed first.
        """
        if not hasattr(self, "binary_path") or not self.binary_path.exists():
            raise RuntimeError("runc binary not downloaded. Run download hook first.")

        # Install binary to system
        self.install_path = install_binary(self.binary_path, "runc", self.COMPONENT_NAME)
