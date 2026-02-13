"""
Etcdctl component installation and management.

Etcdctl is the command-line client for etcd.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class Etcdctl(ComponentBase):
    """
    Etcdctl component for etcd client operations.

    This component handles etcdctl installation for cluster management.
    """

    # Component metadata
    COMPONENT_NAME = "etcdctl"
    CATEGORY = "etcd"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 100

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 180  # 3 minutes
    INSTALL_TIMEOUT = 120  # 2 minutes
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
