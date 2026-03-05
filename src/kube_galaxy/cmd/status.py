"""Status command handler."""

import shutil
from collections.abc import Callable

import typer

from kube_galaxy.pkg.utils.client import (
    get_cluster_info,
    get_context,
    get_nodes,
    get_pods,
    wait_for_nodes,
    wait_for_pods,
)
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import error, info, print_dict, section, success, warning
from kube_galaxy.pkg.utils.shell import run


def status(wait: bool = False, timeout: int = 300) -> None:
    """Display project status and optionally verify cluster health."""
    section("Kubernetes Galaxy Test - Project Status")

    _print_dependency_status()
    _print_cluster_context()

    if wait:
        _verify_cluster_health(timeout)
        success("Cluster is healthy")


def _print_dependency_status() -> None:
    """Print required command dependency status."""
    info("Dependencies:")
    deps = {
        "kubectl": _check_command("kubectl"),
        "spread": _check_command("spread"),
    }
    print_dict(deps)


def _print_cluster_context() -> None:
    """Print active cluster context and current node table if available."""
    if not shutil.which("kubectl"):
        warning("kubectl not available; skipping cluster checks")
        return

    info("")
    try:
        context = get_context()
        info(f"Active Cluster: {context}")
        nodes_output = get_nodes()
        if nodes_output:
            lines = nodes_output.strip().split("\n")
            info(f"Cluster Nodes: {len(lines) - 1}")
            for line in lines[1:]:
                if line:
                    info(f"    {line}")
    except ClusterError:
        info("Active Cluster: error checking")


def _verify_cluster_health(timeout: int) -> None:
    """Wait for cluster readiness and print summary tables."""
    if not shutil.which("kubectl"):
        error("kubectl is required for --wait health checks", show_traceback=False)
        raise typer.Exit(code=1)

    section("Cluster Health Verification")
    info("Waiting for nodes to be Ready...")

    try:
        wait_for_nodes(timeout=timeout)
        wait_for_pods(namespace="kube-system", timeout=timeout)
    except ClusterError as exc:
        error(str(exc), show_traceback=False)
        error("Cluster readiness checks failed", show_traceback=False)
        raise typer.Exit(code=1) from exc

    _print_command_output(get_cluster_info, "Cluster Info")
    _print_command_output(get_nodes, "Nodes")
    _print_command_output(get_pods, "Pods")


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


def _check_command(cmd: str) -> str:
    """Check if a command is installed and return status."""
    if shutil.which(cmd):
        try:
            if cmd == "kubectl":
                result = run(
                    [cmd, "version", "--client"],
                    capture_output=True,
                    check=False,
                )
            else:
                result = run(
                    [cmd, "--version"],
                    capture_output=True,
                    check=False,
                )

            if result.returncode == 0:
                version = result.stdout.strip().split("\n")[0]
                return f"✅ {version}"
            else:
                return "⚠️  installed (version check failed)"
        except Exception:
            return "⚠️  installed (version check error)"
    else:
        return "❌ not installed"
