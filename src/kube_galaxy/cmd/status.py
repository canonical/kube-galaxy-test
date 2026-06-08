"""Status command handler."""

from collections.abc import Callable
from functools import partial

import typer

from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import NodeRole
from kube_galaxy.pkg.units import Unit
from kube_galaxy.pkg.units.juju import JujuUnit
from kube_galaxy.pkg.units.provider import provider_factory
from kube_galaxy.pkg.utils.client import (
    get_cluster_info,
    get_context,
    get_nodes,
    get_pods,
    wait_for_nodes,
    wait_for_pods,
)
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import error, info, section, success, warning
from kube_galaxy.pkg.utils.shell import check_version


def status(manifest_path: str, wait: bool = False, timeout: int = 300) -> None:
    """Display project status and optionally verify cluster health."""
    section("Kubernetes Galaxy Test - Project Status")

    # Load and validate manifest
    manifest = load_manifest(manifest_path)
    # Locate the orchestrator unit via the manifest's provider (no new provisioning)
    provider = provider_factory(manifest)
    lead_unit = provider.locate(NodeRole.CONTROL_PLANE, 0)
    provider.open_tunnels()

    try:
        _print_dependency_status()
        _print_active_manifest(manifest_path)
        _print_cluster_context(lead_unit)
        _print_tunnel_status(provider.locate_all())

        if wait:
            _verify_cluster_health(lead_unit, timeout)
            success("Cluster is healthy")
    finally:
        provider.stop_tunnels()


def _print_dependency_status() -> None:
    """Print required command dependency status."""
    info("Dependencies:")
    check_version("kubectl")


def _print_active_manifest(active: str) -> None:
    """Print the active manifest symlink target if one exists."""
    if active:
        info(f"Active Manifest: {active}")
    else:
        warning("Active Manifest: none (run 'kube-galaxy setup <manifest>' to set one)")


def _print_cluster_context(unit: Unit) -> None:
    """Print active cluster context and current node table if available."""
    info("")
    try:
        context = get_context(unit)
        info(f"Active Cluster: {context}")
        nodes_output = get_nodes(unit)
        if nodes_output:
            lines = nodes_output.strip().split("\n")
            info(f"Cluster Nodes: {len(lines) - 1}")
            for line in lines[1:]:
                if line:
                    info(f"    {line}")
    except ClusterError:
        info("Active Cluster: error checking")


def _print_tunnel_status(units: list[Unit]) -> None:
    """Print SSH reverse tunnel health for Juju units; no-op for other unit types."""
    juju_units = [u for u in units if isinstance(u, JujuUnit)]
    if not juju_units:
        return
    info("")
    info("SSH Tunnel Status:")
    for unit in juju_units:
        status_str = "\u2713 alive" if unit.tunnel_alive() else "\u2717 dead"
        info(f"    {unit.name}: {status_str}")


def _verify_cluster_health(unit: Unit, timeout: int) -> None:
    """Wait for cluster readiness and print summary tables."""

    section("Cluster Health Verification")
    info("Waiting for nodes to be Ready...")

    try:
        wait_for_nodes(unit, timeout=timeout)
        wait_for_pods(unit, namespace="kube-system", timeout=timeout)
    except ClusterError as exc:
        error(str(exc), show_traceback=False)
        error("Cluster readiness checks failed", show_traceback=False)
        raise typer.Exit(code=1) from exc

    _print_command_output(partial(get_cluster_info, unit), "Cluster Info")
    _print_command_output(partial(get_nodes, unit), "Nodes")
    _print_command_output(partial(get_pods, unit), "Pods")


def _print_command_output(command: Callable[[], str], title: str) -> None:
    """Run command and print its output with a section label."""
    info("")
    info(f"{title}:")
    try:
        if output := command().strip():
            info(output)
    except ClusterError as exc:
        error(f"Failed to run: {title}", show_traceback=False)
        raise typer.Exit(code=1) from exc
