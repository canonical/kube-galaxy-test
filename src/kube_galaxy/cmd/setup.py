"""Setup command handler."""

from kube_galaxy.pkg.cluster import setup_cluster
from kube_galaxy.pkg.utils.paths import set_active_manifest


def setup(manifest_path: str) -> None:
    """Provision a Kubernetes cluster from a manifest file."""
    setup_cluster(manifest_path)
    set_active_manifest(manifest_path)
