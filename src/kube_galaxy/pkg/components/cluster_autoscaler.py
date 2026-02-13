"""
Cluster Autoscaler component installation and management.

Cluster Autoscaler automatically adjusts cluster size.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class ClusterAutoscaler(ComponentBase):
    """
    Cluster Autoscaler component for automatic cluster scaling.

    This component handles the Cluster Autoscaler deployment.
    """

    # Component metadata
    COMPONENT_NAME = "cluster-autoscaler"
    CATEGORY = "kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 100

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
