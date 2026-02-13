"""
External provisioner component installation and management.

External provisioner is a CSI helper sidecar for volume provisioning operations.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class ExternalProvisioner(ComponentBase):
    """
    External provisioner component for CSI volume provisioning.

    This component handles the CSI external-provisioner sidecar deployment.
    """

    # Component metadata
    COMPONENT_NAME = "external-provisioner"
    CATEGORY = "kubernetes-csi"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 100

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
