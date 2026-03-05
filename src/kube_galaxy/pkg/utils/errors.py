"""Custom exception types for kube-galaxy."""


class KubeGalaxyError(Exception):
    """Base exception for kube-galaxy errors."""

    pass


class ComponentError(KubeGalaxyError):
    """Component installation or verification error."""

    pass


class ClusterError(KubeGalaxyError):
    """Cluster setup or teardown error."""

    pass
