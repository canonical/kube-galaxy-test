"""
Kube-apiserver component installation and management.

Kube-apiserver is the core API server for Kubernetes.
"""

from typing import ClassVar

from kube_galaxy.pkg.components import ComponentBase, register_component


@register_component
class KubeAPIServer(ComponentBase):
    """
    Kube-APIServer component for Kubernetes control plane.

    This component handles the main API server deployment.
    """

    # Component metadata
    CATEGORY = "kubernetes/kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = []

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
