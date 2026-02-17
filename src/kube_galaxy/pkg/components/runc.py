"""
Runc component installation and management.

Runc is the container runtime specification implementation used by containerd.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


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
        # Use ComponentBase helper to download the binary described in the
        # component config. This centralizes temp dir handling and URL
        # construction.
        self.binary_path = self.download_binary_from_config(arch, "runc")

    def install_hook(self, arch: str) -> None:
        """
        Install runc binary to system using standard install process.
        """
        if not hasattr(self, "binary_path") or not self.binary_path.exists():
            raise RuntimeError("runc binary not downloaded. Run download hook first.")

        # Use base method for standard binary installation
        self.install_path = self.install_downloaded_binary(self.binary_path)
