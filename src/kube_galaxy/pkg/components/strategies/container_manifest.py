"""Install hooks for InstallMethod.CONTAINER_MANIFEST."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from kube_galaxy.pkg.literals import Commands
from kube_galaxy.pkg.utils.client import apply_manifest
from kube_galaxy.pkg.utils.components import download_file, format_component_pattern, source_locally
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError
from kube_galaxy.pkg.utils.gh import gh_download_artifact
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.shell import run

from ._base import _InstallStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _download(comp: ComponentBase) -> None:
    install_cfg = comp.config.installation
    src = format_component_pattern(
        install_cfg.source_format, comp.config, comp.arch_info, install_cfg.repo
    )

    temp_dir = comp.ensure_temp_dir()
    filepath = temp_dir / f"{comp.config.name}-manifest.yaml"
    if install_cfg.repo.is_local:
        source_locally(comp.name, src, filepath)
    elif install_cfg.repo.is_gh_artifact:
        gh_download_artifact(comp.name, src, filepath)
    else:
        if not src.startswith(("http://", "https://")):
            src = f"https://{src}"
        download_file(src, filepath)
        info(f"Downloaded manifest for {comp.config.name}")
    comp.manifest_path = filepath


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
    docs = list(yaml.safe_load_all(docs_str.stdout))
    workloads = [
        doc for doc in docs if doc.get("kind") in ("Deployment", "DaemonSet", "StatefulSet")
    ]
    for workload in workloads:
        kind = workload["kind"].lower()
        name = workload["metadata"]["name"].lower()
        namespace = workload["metadata"].get("namespace", "default").lower()
        run(
            [*Commands.K_ROLLOUT_STATUS, f"{kind}/{name}", "-n", namespace],
            check=True,
            timeout=comp.BOOTSTRAP_TIMEOUT,
        )


_ContainerManifestInstallStrategy = _InstallStrategy(
    download=_download, bootstrap=_bootstrap, verify=_verify
)
