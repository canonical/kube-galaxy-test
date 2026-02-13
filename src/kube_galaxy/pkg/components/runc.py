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
