"""Setup command handler."""

from kube_galaxy.pkg.cluster.setup import setup_cluster


def setup(manifest_path: str) -> None:
    """Provision a Kubernetes cluster from a manifest file."""
    setup_cluster(manifest_path)
