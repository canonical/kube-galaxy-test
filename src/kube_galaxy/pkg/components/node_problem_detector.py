"""
Node Problem Detector component installation and management.

Node Problem Detector detects abnormal node conditions.
"""


def install(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install Node Problem Detector.

    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v0.8.21')
        format: Installation format (Container)
        arch: Architecture (amd64, arm64, etc.)

    Note: Node Problem Detector is deployed as a Kubernetes addon through manifests.
    This install function serves as a placeholder for consistency.
    """
    pass


def configure() -> None:
    """
    Configure Node Problem Detector.

    Configuration happens through Kubernetes manifests after cluster bootstrap.
    """
    pass


def remove() -> None:
    """
    Remove Node Problem Detector.

    Cleanup is handled through kubectl deletion or kubeadm reset.
    """
    pass
