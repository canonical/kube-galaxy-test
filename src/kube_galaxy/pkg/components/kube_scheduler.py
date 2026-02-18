"""
Kube-scheduler component installation and management.

Kube-scheduler schedules pods to nodes.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class KubeScheduler(ComponentBase):
    """
    Kube-Scheduler component for pod scheduling.

    This component handles pod scheduling to nodes.
    """

    # Component metadata
    CATEGORY = "kubernetes/kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = []

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
