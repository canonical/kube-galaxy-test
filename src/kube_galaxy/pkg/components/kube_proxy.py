"""
Kube-proxy component installation and management.

Kube-proxy handles Kubernetes service networking.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class KubeProxy(ComponentBase):
    """
    Kube-Proxy component for service networking.

    This component handles service networking and load balancing.
    """

    # Component metadata
    CATEGORY = "kubernetes/kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = []

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
