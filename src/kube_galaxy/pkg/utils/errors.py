"""Custom exception types for kube-galaxy."""


class KubeGalaxyError(Exception):
    """Base exception for kube-galaxy errors."""

    pass


class ManifestError(KubeGalaxyError):
    """Manifest validation or parsing error."""

    pass


class ArchitectureError(KubeGalaxyError):
    """Architecture detection or mapping error."""

    pass


class ComponentError(KubeGalaxyError):
    """Component installation or verification error."""

    pass


class ClusterError(KubeGalaxyError):
    """Cluster setup or teardown error."""

    pass
