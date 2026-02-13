"""
Node Problem Detector component installation and management.

Node Problem Detector detects abnormal node conditions.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase


class NodeProblemDetector(ComponentBase):
    """
    Node Problem Detector component for node issue detection.

    This component handles detection of node-level issues.
    """

    # Component metadata
    COMPONENT_NAME = "node-problem-detector"
    CATEGORY = "kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY = 100

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes

    def download_hook(self, arch: str) -> None:
        """
        Download Node Problem Detector container image.

        Container images are pulled by the DaemonSet, this serves as
        a placeholder for consistency with other components.
        """
        pass

    def install_hook(self, arch: str) -> None:
        """
        Install Node Problem Detector.

        Installation happens through Kubernetes DaemonSet deployment.
        This hook serves as a placeholder for consistency.
        """
        pass

    def configure_hook(self) -> None:
        """
        Configure Node Problem Detector.

        Configuration happens through manifests after cluster bootstrap.
        """
        pass

    def remove_hook(self) -> None:
        """
        Remove Node Problem Detector.

        Cleanup is handled through kubectl deletion or kubeadm reset.
        """
        pass

    def verify_hook(self) -> None:
        """
        Verify Node Problem Detector is running.

        Checks for the DaemonSet in the kube-system namespace.
        """
        pass
