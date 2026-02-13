"""
CoreDNS component installation and management.

CoreDNS is the DNS server used by Kubernetes.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class CoreDNS(ComponentBase):
    """
    CoreDNS component for cluster DNS services.

    This component handles the CoreDNS deployment for Kubernetes DNS.
    """

    # Component metadata
    COMPONENT_NAME = "coredns"
    CATEGORY = "coredns"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 100

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
