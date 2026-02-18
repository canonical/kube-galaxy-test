"""
Etcd component installation and management.

Etcd is the key-value store backing Kubernetes.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class Etcd(ComponentBase):
    """
    Etcd component for Kubernetes datastore.

    This component handles etcd installation and configuration.
    """

    # Component metadata
    CATEGORY = "etcd"
    DEPENDENCIES: ClassVar[list[str]] = []

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 180  # 3 minutes
    INSTALL_TIMEOUT = 120  # 2 minutes
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
