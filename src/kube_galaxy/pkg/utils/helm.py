"""Helm client operations wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.units import RunResult, Unit
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import info, success
from kube_galaxy.pkg.utils.shell import ShellError


def helm(unit: Unit, *cmd: str, **kwargs: Any) -> RunResult:
    """Run a helm command on the unit.

    Args:
        unit: Unit on which to run helm
        *cmd: helm subcommand and arguments
        **kwargs: Passed through to unit.run() (check, timeout, privileged)

    Returns:
        RunResult from the command execution
    """
    env = {"KUBECONFIG": str(SystemPaths.kube_config())}
    return unit.run(["helm", *cmd], env=env, **kwargs)


def helm_repo_add(unit: Unit, name: str, url: str) -> None:
    """Add a helm chart repository and update the repo index.

    Uses --force-update so repeated calls are idempotent.

    Args:
        unit: Unit on which to run helm
        name: Repository name (e.g. "projectcalico")
        url: Repository URL (e.g. "https://docs.tigera.io/calico/charts")

    Raises:
        ClusterError: If repo add fails
    """
    try:
        info(f"Adding helm repo: {name} ({url})")
        helm(unit, "repo", "add", name, url, "--force-update", check=True)
        helm(unit, "repo", "update", check=True)
        success(f"Helm repo added: {name}")
    except ShellError as exc:
        raise ClusterError(f"Failed to add helm repo {name}: {exc}") from exc


def helm_install_from_repo(unit: Unit, release: str, chart: str) -> None:
    """Install a helm chart from a previously added repository.

    Args:
        unit: Unit on which to run helm
        release: Release name (e.g. "calico")
        chart: Chart reference (e.g. "projectcalico/tigera-operator")

    Raises:
        ClusterError: If helm install fails
    """
    try:
        info(f"Installing helm release: {release} (chart: {chart})")
        helm(unit, "install", release, chart, check=True)
        success(f"Helm release installed: {release}")
    except ShellError as exc:
        raise ClusterError(f"Failed to install helm release {release}: {exc}") from exc


def helm_install_from_archive(unit: Unit, release: str, chart_path: Path) -> None:
    """Install a helm chart from a local chart archive.

    Pushes the chart archive to the unit and runs helm install from it.

    Args:
        unit: Unit on which to run helm
        release: Release name (e.g. "calico")
        chart_path: Local path to the chart archive (.tgz)

    Raises:
        ClusterError: If helm install fails
    """
    remote_chart = "/tmp/helm_chart.tgz"
    try:
        info(f"Installing helm release: {release} (chart: {chart_path.name})")
        unit.put(chart_path, remote_chart)
        helm(unit, "install", release, remote_chart, check=True)
        success(f"Helm release installed: {release}")
    except ShellError as exc:
        raise ClusterError(f"Failed to install helm release {release}: {exc}") from exc
    finally:
        unit.run(["rm", "-f", remote_chart], check=False)


def helm_uninstall(unit: Unit, release: str) -> None:
    """Uninstall a helm release.

    Args:
        unit: Unit on which to run helm
        release: Release name to uninstall

    Raises:
        ClusterError: If helm uninstall fails
    """
    try:
        info(f"Uninstalling helm release: {release}")
        helm(unit, "uninstall", release, check=True)
        success(f"Helm release uninstalled: {release}")
    except ShellError as exc:
        raise ClusterError(f"Failed to uninstall helm release {release}: {exc}") from exc
