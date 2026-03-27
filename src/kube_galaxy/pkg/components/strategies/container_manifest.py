"""Install hooks for InstallMethod.CONTAINER_MANIFEST."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kube_galaxy.pkg.utils.client import apply_manifest, create, kubectl
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError

from ._base import _fetch_to_temp, _InstallStrategy, only_lead_control_plane

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


@only_lead_control_plane
def _download(comp: ComponentBase) -> None:
    comp.manifest_path = _fetch_to_temp(comp)


@only_lead_control_plane
def _bootstrap(comp: ComponentBase) -> None:
    comp_name = comp.config.name
    if not comp.manifest_path or not comp.manifest_path.exists():
        raise ComponentError(f"{comp_name} manifest not downloaded. Run download hook first.")
    try:
        apply_manifest(comp.unit, comp.manifest_path)
    except ClusterError as e:
        raise ComponentError(f"Failed to apply manifest for {comp_name}") from e


@only_lead_control_plane
def _verify(comp: ComponentBase) -> None:
    if not comp.manifest_path or not comp.manifest_path.exists():
        raise ComponentError(f"{comp.config.name} manifest not downloaded")

    # yaml.safe_load_all may yield None or non-mapping documents (e.g. for empty YAML docs).
    # Restrict to dicts before attempting to access mapping methods/keys.
    results = create(comp.unit, dry_run=True, file=comp.manifest_path)
    docs = [doc for doc in results if isinstance(doc, dict)]

    for doc in docs:
        kind = doc.get("kind")
        if kind not in ("Deployment", "DaemonSet", "StatefulSet"):
            continue

        metadata = doc.get("metadata")
        if not isinstance(metadata, dict):
            continue

        name = metadata.get("name")
        if not isinstance(name, str):
            continue

        namespace = metadata.get("namespace", "default")
        if not isinstance(namespace, str):
            namespace = "default"

        kubectl(
            comp.unit,
            "rollout",
            "status",
            f"{kind.lower()}/{name.lower()}",
            "-n",
            namespace.lower(),
            timeout=comp.BOOTSTRAP_TIMEOUT,
        )


_ContainerManifestInstallStrategy = _InstallStrategy(
    download=_download, bootstrap=_bootstrap, verify=_verify
)
