"""
Pause component installation and management.

The pause container is used for infrastructure.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class Pause(ComponentBase):
    """
    Pause component for Kubernetes infrastructure.

    This component handles the pause container deployment.
    """

    # Component metadata
    COMPONENT_NAME = "pause"
    CATEGORY = "kubernetes/kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 100

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
