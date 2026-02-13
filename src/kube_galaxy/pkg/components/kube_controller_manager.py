"""
Kube-controller-manager component installation and management.

Kube-controller-manager runs Kubernetes controllers.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class KubeControllerManager(ComponentBase):
    """
    Kube-ControllerManager component for Kubernetes control loops.

    This component handles the controller manager deployment.
    """

    # Component metadata
    COMPONENT_NAME = "kube-controller-manager"
    CATEGORY = "kubernetes/kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 100

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
