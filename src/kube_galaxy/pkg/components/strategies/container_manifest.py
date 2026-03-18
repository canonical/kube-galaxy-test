"""Install hooks for InstallMethod.CONTAINER_MANIFEST."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from kube_galaxy.pkg.literals import Commands
from kube_galaxy.pkg.utils.client import apply_manifest
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError
from kube_galaxy.pkg.utils.shell import run

from ._base import _fetch_to_temp, _InstallStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _download(comp: ComponentBase) -> None:
    comp.manifest_path = _fetch_to_temp(comp)


def _bootstrap(comp: ComponentBase) -> None:
    comp_name = comp.config.name
    if not comp.manifest_path or not comp.manifest_path.exists():
        raise ComponentError(f"{comp_name} manifest not downloaded. Run download hook first.")
    try:
        apply_manifest(comp.manifest_path)
    except ClusterError as e:
        raise ComponentError(f"Failed to apply manifest for {comp_name}") from e


def _verify(comp: ComponentBase) -> None:
    if not comp.manifest_path or not comp.manifest_path.exists():
        raise ComponentError(f"{comp.config.name} manifest not downloaded")

    docs_str = run(
        [*Commands.K_CREATE_DRY_RUN, "-f", str(comp.manifest_path)],
        check=True,
        capture_output=True,
    )
    # yaml.safe_load_all may yield None or non-mapping documents (e.g. for empty YAML docs).
    # Restrict to dicts before attempting to access mapping methods/keys.
    docs = [doc for doc in yaml.safe_load_all(docs_str.stdout) if isinstance(doc, dict)]

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

        run(
            [*Commands.K_ROLLOUT_STATUS, f"{kind.lower()}/{name.lower()}", "-n", namespace.lower()],
            check=True,
            timeout=comp.BOOTSTRAP_TIMEOUT,
        )


_ContainerManifestInstallStrategy = _InstallStrategy(
    download=_download, bootstrap=_bootstrap, verify=_verify
)
