"""
External attacher component installation and management.

External attacher is a CSI helper sidecar for volume attachment operations.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class ExternalAttacher(ComponentBase):
    """
    External attacher component for CSI volume attachment.

    This component handles the CSI external-attacher sidecar deployment.
    """

    # Component metadata
    COMPONENT_NAME = "external-attacher"
    CATEGORY = "kubernetes-csi"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 100

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
