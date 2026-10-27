"""log command handler."""

from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import NodeRole
from kube_galaxy.pkg.units.provider import provider_factory
from kube_galaxy.pkg.utils.logging import section
from kube_galaxy.pkg.utils.logs import collect_kubernetes_logs


def logs(manifest_path: str) -> None:
    """Collect and display Kubernetes logs."""
    section("Kubernetes Galaxy Test - Collect Cluster Logs")

    # Load and validate manifest
    manifest = load_manifest(manifest_path)
    # Locate the orchestrator unit via the manifest's provider (no new provisioning)
    provider = provider_factory(manifest)
    lead_unit = provider.locate(NodeRole.CONTROL_PLANE, 0)

    collect_kubernetes_logs(lead_unit)
