"""Setup command handler."""

from pathlib import Path

import typer

from kube_galaxy.pkg.cluster import setup_cluster
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.utils.kubeconfig import (
    KUBE_GALAXY_CONTEXT,
    is_interactive,
    merge_kube_galaxy_context,
)
from kube_galaxy.pkg.utils.logging import info, success
from kube_galaxy.pkg.utils.paths import set_active_manifest


def setup(manifest_path: str, update_kubeconfig: bool = False) -> None:
    """Provision a Kubernetes cluster from a manifest file.

    Args:
        manifest_path: Path to the cluster manifest YAML.
        update_kubeconfig: When ``True`` the ``kube-galaxy`` context is merged
            into ``$HOME/.kube/config`` without prompting the user.  When
            ``False`` (default) the user is asked interactively (if stdin is a
            terminal).
    """
    setup_cluster(manifest_path)
    set_active_manifest(manifest_path)
    _handle_kubeconfig_adjustment(update_kubeconfig)


def _handle_kubeconfig_adjustment(update_kubeconfig: bool) -> None:
    """Optionally merge the kube-galaxy context into ~/.kube/config."""
    source = SystemPaths.local_kube_config()
    if not source.exists():
        return

    if update_kubeconfig:
        _merge_context(source)
    elif is_interactive():
        if typer.confirm(
            f"\nAdd '{KUBE_GALAXY_CONTEXT}' context to ~/.kube/config?",
            default=True,
        ):
            _merge_context(source)
        else:
            info(f"Skipped: ~/.kube/config not updated. Kubeconfig is at: {source}")


def _merge_context(source_path: Path) -> None:
    """Merge the kube-galaxy context and log the outcome."""
    merge_kube_galaxy_context(source_path)
    success(
        f"Updated ~/.kube/config: context '{KUBE_GALAXY_CONTEXT}' is now active.\n"
        f"  Run 'kubectl get nodes' to verify the cluster is reachable."
    )
