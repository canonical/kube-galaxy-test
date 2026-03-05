"""Kubernetes client operations wrapper."""

import json
import shutil
from pathlib import Path
from typing import Any

from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import info, success, warning
from kube_galaxy.pkg.utils.shell import ShellError, run


def verify_connectivity() -> None:
    """
    Verify kubectl connectivity to Kubernetes cluster.

    Raises:
        ClusterError: If kubectl is not available or cannot connect to cluster
    """
    if not shutil.which("kubectl"):
        raise ClusterError("kubectl not found in PATH")

    try:
        info("Verifying cluster connectivity...")
        run(["kubectl", "cluster-info"], check=True, capture_output=True)
        success("Connected to Kubernetes cluster")
    except ShellError as exc:
        raise ClusterError(f"Failed to connect to cluster: {exc}") from exc


def get_context() -> str:
    """
    Get the current Kubernetes context.

    Returns:
        Current context name

    Raises:
        ClusterError: If context cannot be determined
    """
    try:
        result = run(
            ["kubectl", "config", "current-context"], check=True, capture_output=True, text=True
        )
        return result.stdout.strip()
    except ShellError as exc:
        raise ClusterError(f"Failed to get current context: {exc}") from exc


def wait_for_nodes(timeout: int = 300, condition: str = "Ready") -> None:
    """
    Wait for all nodes to reach a specified condition.

    Args:
        timeout: Maximum seconds to wait
        condition: Node condition to wait for (default: Ready)

    Raises:
        ClusterError: If nodes do not reach condition within timeout
    """
    try:
        info(f"Waiting for nodes to be {condition}...")
        run(
            [
                "kubectl",
                "wait",
                f"--for=condition={condition}",
                "nodes",
                "--all",
                f"--timeout={timeout}s",
            ],
            check=True,
            capture_output=True,
        )
        success(f"All nodes are {condition}")
    except ShellError as exc:
        raise ClusterError(f"Nodes failed to reach {condition} condition: {exc}") from exc


def wait_for_pods(
    namespace: str = "kube-system", timeout: int = 300, condition: str = "Ready"
) -> None:
    """
    Wait for pods in a namespace to reach a specified condition.

    Args:
        namespace: Kubernetes namespace to monitor (default: kube-system)
        timeout: Maximum seconds to wait
        condition: Pod condition to wait for (default: Ready)

    Raises:
        ClusterError: If pods do not reach condition within timeout
    """
    try:
        info(f"Waiting for pods in {namespace} to be {condition}...")
        run(
            [
                "kubectl",
                "wait",
                f"--for=condition={condition}",
                "pod",
                "--all",
                "-n",
                namespace,
                f"--timeout={timeout}s",
            ],
            check=True,
            capture_output=True,
        )
        success(f"Pods in {namespace} are {condition}")
    except ShellError as exc:
        raise ClusterError(f"Pods in {namespace} failed to reach {condition}: {exc}") from exc


def get_api_server_status(timeout: int = 300) -> None:
    """
    Check API server readiness via /readyz endpoint.

    Args:
        timeout: Maximum seconds to wait

    Raises:
        ClusterError: If API server is not ready
    """
    try:
        info("Checking API server readiness...")
        run(
            [
                "kubectl",
                "get",
                "--raw=/readyz",
                f"--request-timeout={timeout}s",
            ],
            check=True,
            capture_output=True,
        )
        success("API server is ready")
    except ShellError as exc:
        raise ClusterError(f"API server not ready: {exc}") from exc


def get_cluster_info() -> str:
    """
    Get cluster information.

    Returns:
        Cluster info as string

    Raises:
        ClusterError: If cluster info cannot be retrieved
    """
    try:
        result = run(["kubectl", "cluster-info"], check=True, capture_output=True, text=True)
        return result.stdout
    except ShellError as exc:
        raise ClusterError(f"Failed to retrieve cluster info: {exc}") from exc


def get_nodes(wide: bool = False) -> str:
    """
    Get nodes information.

    Args:
        wide: Return wide output (includes internal IP, kernel version, etc.)

    Returns:
        Node information as string

    Raises:
        ClusterError: If node info cannot be retrieved
    """
    try:
        cmd = ["kubectl", "get", "nodes"]
        if wide:
            cmd.append("-o")
            cmd.append("wide")
        result = run(cmd, check=True, capture_output=True, text=True)
        return result.stdout
    except ShellError as exc:
        raise ClusterError(f"Failed to retrieve nodes: {exc}") from exc


def get_pods(namespace: str = "", wide: bool = False, output_format: str = "") -> str:
    """
    Get pods information.

    Args:
        namespace: Kubernetes namespace (empty = all namespaces)
        wide: Return wide output
        output_format: Output format (json, yaml, etc.)

    Returns:
        Pod information as string

    Raises:
        ClusterError: If pod info cannot be retrieved
    """
    try:
        cmd = ["kubectl", "get", "pods"]

        if not namespace:
            cmd.append("-A")
        else:
            cmd.extend(["-n", namespace])

        if wide:
            cmd.extend(["-o", "wide"])
        elif output_format:
            cmd.extend(["-o", output_format])

        result = run(cmd, check=True, capture_output=True, text=True)
        return result.stdout
    except ShellError as exc:
        raise ClusterError(f"Failed to retrieve pods: {exc}") from exc


def get_pod_data_json(namespace: str = "") -> list[dict[str, Any]]:
    """
    Get pods information as JSON for structured parsing.

    Args:
        namespace: Kubernetes namespace (empty = all namespaces)

    Returns:
        List of pod dictionaries

    Raises:
        ClusterError: If pod data cannot be retrieved
    """
    try:
        cmd = ["kubectl", "get", "pods"]
        if not namespace:
            cmd.append("-A")
        else:
            cmd.extend(["-n", namespace])
        cmd.extend(["-o", "json"])

        result = run(cmd, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        items: list[dict[str, Any]] = data.get("items", [])
        return items
    except (ShellError, json.JSONDecodeError) as exc:
        raise ClusterError(f"Failed to retrieve pods data: {exc}") from exc


def describe_nodes() -> str:
    """
    Get detailed node descriptions.

    Returns:
        Node descriptions as string

    Raises:
        ClusterError: If descriptions cannot be retrieved
    """
    try:
        result = run(["kubectl", "describe", "nodes"], check=True, capture_output=True, text=True)
        return result.stdout
    except ShellError as exc:
        raise ClusterError(f"Failed to describe nodes: {exc}") from exc


def get_events(namespace: str = "", all_namespaces: bool = True) -> str:
    """
    Get Kubernetes events.

    Args:
        namespace: Specific namespace (ignored if all_namespaces=True)
        all_namespaces: Get events from all namespaces (default: True)

    Returns:
        Events as string

    Raises:
        ClusterError: If events cannot be retrieved
    """
    try:
        cmd = ["kubectl", "get", "events"]
        if all_namespaces:
            cmd.append("-A")
        elif namespace:
            cmd.extend(["-n", namespace])

        result = run(cmd, check=True, capture_output=True, text=True)
        return result.stdout
    except ShellError as exc:
        raise ClusterError(f"Failed to retrieve events: {exc}") from exc


def get_pod_logs(namespace: str, pod_name: str, tail: int = 100) -> str:
    """
    Get logs from a specific pod.

    Args:
        namespace: Kubernetes namespace
        pod_name: Pod name
        tail: Number of lines to retrieve from end of logs

    Returns:
        Pod logs as string. Returns empty string if pod has no logs.
    """
    result = run(
        ["kubectl", "logs", "-n", namespace, pod_name, f"--tail={tail}"],
        check=False,
        capture_output=True,
        text=True,
    )
    # Non-zero exit is OK if pod has no logs; return empty
    return result.stdout if result.returncode == 0 else ""


def create_namespace(name: str, labels: dict[str, str] | None = None) -> None:
    """
    Create a Kubernetes namespace with optional labels.

    Args:
        name: Namespace name
        labels: Optional dict of labels to apply

    Raises:
        ClusterError: If namespace creation fails
    """
    try:
        info(f"Creating namespace: {name}")
        run(["kubectl", "create", "namespace", name], check=True, capture_output=True)

        if labels:
            label_strs = [f"{k}={v}" for k, v in labels.items()]
            run(
                ["kubectl", "label", "namespace", name, *label_strs],
                check=True,
                capture_output=True,
            )
            success(f"Namespace created with labels: {name}")
        else:
            success(f"Namespace created: {name}")

    except ShellError as exc:
        raise ClusterError(f"Failed to create namespace {name}: {exc}") from exc


def delete_namespace(name: str, timeout: int = 60) -> None:
    """
    Delete a Kubernetes namespace with timeout.

    Args:
        name: Namespace name
        timeout: Maximum seconds to wait for deletion

    Raises:
        ClusterError: If namespace deletion fails (actual error, not not-found)
    """
    try:
        info(f"Deleting namespace: {name}")
        run(
            ["kubectl", "delete", "namespace", name, "--timeout", f"{timeout}s"],
            check=True,
            capture_output=True,
        )
        success(f"Namespace deleted: {name}")
    except ShellError as exc:
        # Don't fail if namespace doesn't exist
        if "not found" in str(exc).lower():
            warning(f"Namespace {name} not found (may already be deleted)")
        else:
            raise ClusterError(f"Failed to delete namespace {name}: {exc}") from exc


def apply_manifest(manifest_path: Path | str) -> None:
    """
    Apply a Kubernetes manifest file.

    Args:
        manifest_path: Path to manifest file

    Raises:
        ClusterError: If manifest application fails
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise ClusterError(f"Manifest not found: {manifest_path}")

    try:
        info(f"Applying manifest: {manifest_path.name}")
        run(["kubectl", "apply", "-f", str(manifest_path)], check=True, capture_output=True)
        success(f"Manifest applied: {manifest_path.name}")
    except ShellError as exc:
        raise ClusterError(f"Failed to apply manifest {manifest_path}: {exc}") from exc
