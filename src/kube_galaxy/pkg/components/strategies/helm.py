"""Install hooks for InstallMethod.HELM."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from kube_galaxy.pkg.utils.client import kubectl
from kube_galaxy.pkg.utils.helm import (
    helm,
    helm_install_from_archive,
    helm_install_from_repo,
    helm_repo_add,
)
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError

from ._base import _fetch_to_temp, _InstallStrategy, only_lead_control_plane

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


@only_lead_control_plane
def _download(comp: ComponentBase) -> None:
    """Download helm chart artifacts.

    When helm_repo is True, adds the chart repository from repo.base_url so
    the chart reference in source_format can be resolved during bootstrap.
    Otherwise, downloads the chart archive (.tgz) from the rendered source_format URL.
    """
    install_cfg = comp.config.installation

    if install_cfg.helm_repo:
        # source_format is a chart ref like "projectcalico/tigera-operator"
        # repo name is the prefix before "/"
        repo_name = install_cfg.source_format.split("/")[0]
        helm_repo_add(comp.unit, repo_name, install_cfg.repo.base_url)
    else:
        comp.chart_path = _fetch_to_temp(comp)


@only_lead_control_plane
def _bootstrap(comp: ComponentBase) -> None:
    """Install the helm chart.

    Uses helm_install_from_repo when helm_repo is True (chart reference from
    an added repository), otherwise installs from the locally downloaded
    chart archive.
    """
    comp_name = comp.config.name
    install_cfg = comp.config.installation

    try:
        if install_cfg.helm_repo:
            helm_install_from_repo(comp.unit, comp_name, install_cfg.source_format)
        else:
            if not comp.chart_path or not comp.chart_path.exists():
                raise ComponentError(
                    f"{comp_name} chart not downloaded. Run download hook first."
                )
            helm_install_from_archive(comp.unit, comp_name, comp.chart_path)
    except ClusterError as e:
        raise ComponentError(f"Failed to install helm chart for {comp_name}") from e


@only_lead_control_plane
def _verify(comp: ComponentBase) -> None:
    """Verify the helm release is deployed and all workloads are rolled out.

    Retrieves the rendered manifests from the helm release and checks rollout
    status for all Deployments, DaemonSets, and StatefulSets.
    """
    comp_name = comp.config.name

    # Get the rendered manifests that helm actually deployed
    try:
        result = helm(comp.unit, "get", "manifest", comp_name, check=True)
    except Exception as e:
        raise ComponentError(f"Failed to get helm manifest for {comp_name}") from e

    docs = [doc for doc in yaml.safe_load_all(result.stdout) if isinstance(doc, dict)]

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


_HelmInstallStrategy = _InstallStrategy(
    download=_download, bootstrap=_bootstrap, verify=_verify
)

