"""Kubernetes log collection and debugging utilities."""

from datetime import datetime
from pathlib import Path

from kube_galaxy.pkg.utils.client import (
    describe_nodes,
    get_cluster_info,
    get_events,
    get_nodes,
    get_pod_data_json,
    get_pod_logs,
    get_pods,
)
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import info, section, success, warning


def collect_kubernetes_logs(output_dir: str = "debug-logs") -> str:
    """
    Collect Kubernetes cluster logs for debugging.

    Args:
        output_dir: Directory to save collected logs

    Returns:
        Path to debug logs directory

    Raises:
        ClusterError: If log collection fails
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    section("Collecting Kubernetes Logs")

    try:
        # Collect cluster info
        _collect_cluster_info(output_path)

        # Collect node info
        _collect_node_info(output_path)

        # Collect pod logs
        _collect_pod_logs(output_path)

        # Collect events
        _collect_events(output_path)

        # Collect system logs
        _collect_system_logs(output_path)

        section("Log Collection Complete")
        success(f"Logs collected to: {output_path.absolute()}")
        return str(output_path.absolute())

    except Exception as exc:
        raise ClusterError(f"Failed to collect Kubernetes logs: {exc}") from exc


def _collect_cluster_info(output_path: Path) -> None:
    """Collect cluster information."""
    info("Collecting cluster information...")

    try:
        cluster_info = get_cluster_info()
        (output_path / "cluster-info.txt").write_text(cluster_info)
        success("  Cluster info saved")
    except ClusterError as exc:
        warning(f"  Failed to collect cluster info: {exc}")


def _collect_node_info(output_path: Path) -> None:
    """Collect node information."""
    info("Collecting node information...")

    try:
        # Get node descriptions
        node_descriptions = describe_nodes()
        (output_path / "nodes-describe.txt").write_text(node_descriptions)

        # Get node status
        node_status = get_nodes(wide=True)
        (output_path / "nodes-status.txt").write_text(node_status)

        success("  Node info saved")
    except ClusterError as exc:
        warning(f"  Failed to collect node info: {exc}")


def _collect_pod_logs(output_path: Path) -> None:
    """Collect pod logs from all namespaces."""
    info("Collecting pod logs...")

    pods_dir = output_path / "pods"
    pods_dir.mkdir(exist_ok=True)

    try:
        # Get all pods
        pods_data = get_pod_data_json()
        pod_count = 0

        for pod_item in pods_data:
            namespace = pod_item["metadata"]["namespace"]
            pod_name = pod_item["metadata"]["name"]

            # Get pod logs
            log_content = get_pod_logs(namespace, pod_name, tail=100)

            log_dir = pods_dir / namespace / pod_name
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "logs.txt").write_text(log_content)

            pod_count += 1

        success(f"  Pod logs saved ({pod_count} pods)")

    except ClusterError as exc:
        warning(f"  Failed to collect pod logs: {exc}")


def _collect_events(output_path: Path) -> None:
    """Collect Kubernetes events."""
    info("Collecting events...")

    try:
        events = get_events(all_namespaces=True)
        (output_path / "events.txt").write_text(events)
        success("  Events saved")
    except ClusterError as exc:
        warning(f"  Failed to collect events: {exc}")


def _collect_system_logs(output_path: Path) -> None:
    """Collect system-level logs."""
    info("Collecting system logs...")

    try:
        # Get kube-system namespace pods
        pods_str = get_pods(namespace="kube-system", wide=True)
        (output_path / "kube-system-pods.txt").write_text(pods_str)

        # Events are now collected from all namespaces in _collect_events()
        # so we don't need a separate kube-system events call
        success("  System logs saved")
    except ClusterError as exc:
        warning(f"  Failed to collect system logs: {exc}")


def create_debug_issue(logs_dir: str = "debug-logs") -> str:
    """
    Create a markdown debug summary from collected logs.

    Args:
        logs_dir: Directory containing collected logs

    Returns:
        Markdown formatted debug information
    """
    logs_path = Path(logs_dir)

    markdown = "# Debug Information\n\n"
    markdown += f"Collected at: {datetime.now().isoformat()}\n\n"

    # Include cluster info
    cluster_info_file = logs_path / "cluster-info.txt"
    if cluster_info_file.exists():
        markdown += "## Cluster Info\n\n"
        markdown += f"```\n{cluster_info_file.read_text()}\n```\n\n"

    # Include node status
    nodes_status_file = logs_path / "nodes-status.txt"
    if nodes_status_file.exists():
        markdown += "## Node Status\n\n"
        markdown += f"```\n{nodes_status_file.read_text()}\n```\n\n"

    # Include events summary
    events_file = logs_path / "events.txt"
    if events_file.exists():
        markdown += "## Recent Events\n\n"
        events_text = events_file.read_text()
        lines = events_text.split("\n")[:20]  # First 20 lines
        markdown += f"```\n{''.join(lines)}\n```\n\n"

    return markdown
