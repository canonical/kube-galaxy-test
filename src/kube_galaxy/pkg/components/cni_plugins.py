"""
CNI Plugins component installation and management.

CNI (Container Network Interface) plugins provide networking for Kubernetes.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class CNIPlugins(ComponentBase):
    """
    CNI Plugins component for cluster networking.

    This component handles CNI plugin installation for Kubernetes networking.
    """

    # Component metadata
    COMPONENT_NAME = "cni-plugins"
    CATEGORY = "container-networking"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 50

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 120  # 2 minutes
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
