"""Install hooks for InstallMethod.CONTAINER_MANIFEST."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from kube_galaxy.pkg.manifest.models import NodeRole
from kube_galaxy.pkg.utils.client import apply_manifest, create, kubectl
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError

from ._base import _fetch_to_temp, _InstallStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase

    CompCallable = Callable[[ComponentBase], None]


def skip_if_not_control_plane(func: CompCallable) -> CompCallable:
    """Skip install hooks for non-control-plane units since they won't have kubectl access."""

    def wrapper(comp: ComponentBase) -> None:
        if (comp.unit.role, comp.unit.index) != (NodeRole.CONTROL_PLANE, 0):
            return  # Skip non-control-plane units
        return func(comp)

    return wrapper


@skip_if_not_control_plane
def _download(comp: ComponentBase) -> None:
    comp.manifest_path = _fetch_to_temp(comp)


@skip_if_not_control_plane
def _bootstrap(comp: ComponentBase) -> None:
    comp_name = comp.config.name
    if (comp.unit.role, comp.unit.index) != (NodeRole.CONTROL_PLANE, 0):
        return  # Only bootstrap on the first control-plane unit
    if not comp.manifest_path or not comp.manifest_path.exists():
        raise ComponentError(f"{comp_name} manifest not downloaded. Run download hook first.")
    try:
        apply_manifest(comp.unit, comp.manifest_path)
    except ClusterError as e:
        raise ComponentError(f"Failed to apply manifest for {comp_name}") from e


@skip_if_not_control_plane
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
