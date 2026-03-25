"""Kubernetes client operations wrapper."""

import json
from pathlib import Path
from typing import Any

import yaml

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.units import RunResult, Unit
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import info, success, warning
from kube_galaxy.pkg.utils.shell import ShellError


def kubectl(unit: Unit, *cmd: str, **kwargs: Any) -> RunResult:
    """Run a kubectl command on the kubelet unit."""
    env = {"KUBECONFIG": str(SystemPaths.kube_config())}
    return unit.run(["kubectl", *cmd], env=env, **kwargs)


def verify_connectivity(unit: Unit) -> None:
    """
    Verify kubectl connectivity to Kubernetes cluster.

    Raises:
        ClusterError: If kubectl is not available or cannot connect to cluster
    """
    try:
        info("Verifying cluster connectivity...")
        kubectl(unit, "version", check=True)
        success("Connected to Kubernetes cluster")
    except ShellError as exc:
        raise ClusterError(f"Failed to connect to cluster: {exc}") from exc


def get_context(unit: Unit) -> str:
    """
    Get the current Kubernetes context.

    Returns:
        Current context name

    Raises:
        ClusterError: If context cannot be determined
    """
    try:
        result = kubectl(unit, "config", "current-context", check=True)
        return result.stdout.strip()
    except ShellError as exc:
        raise ClusterError(f"Failed to get current context: {exc}") from exc


def wait_for_nodes(unit: Unit, timeout: int = 300, condition: str = "Ready") -> None:
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
        kubectl(
            unit,
            "wait",
            f"--for=condition={condition}",
            "nodes",
            "--all",
            f"--timeout={timeout}s",
            check=True,
        )
        success(f"All nodes are {condition}")
    except ShellError as exc:
        raise ClusterError(f"Nodes failed to reach {condition} condition: {exc}") from exc


def wait_for_pods(
    unit: Unit, namespace: str = "kube-system", timeout: int = 300, condition: str = "Ready"
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
        kubectl(
            unit,
            "wait",
            f"--for=condition={condition}",
            "pod",
            "--all",
            "-n",
            namespace,
            f"--timeout={timeout}s",
            check=True,
        )
        success(f"Pods in {namespace} are {condition}")
    except ShellError as exc:
        raise ClusterError(f"Pods in {namespace} failed to reach {condition}: {exc}") from exc


def get_api_server_status(unit: Unit, timeout: int = 300) -> None:
    """
    Check API server readiness via /readyz endpoint.

    Args:
        timeout: Maximum seconds to wait

    Raises:
        ClusterError: If API server is not ready
    """
    try:
        info("Checking API server readiness...")
        kubectl(
            unit,
            "get",
            "--raw=/readyz",
            f"--request-timeout={timeout}s",
            check=True,
        )
        success("API server is ready")
    except ShellError as exc:
        raise ClusterError(f"API server not ready: {exc}") from exc


def get_cluster_info(unit: Unit) -> str:
    """
    Get cluster information.

    Returns:
        Cluster info as string

    Raises:
        ClusterError: If cluster info cannot be retrieved
    """
    try:
        result = kubectl(
            unit,
            "cluster-info",
            check=True,
        )
        return result.stdout
    except ShellError as exc:
        raise ClusterError(f"Failed to retrieve cluster info: {exc}") from exc


def get_nodes(unit: Unit, wide: bool = False) -> str:
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
        cmd = ["get", "nodes"]
        if wide:
            cmd.append("-o")
            cmd.append("wide")
        result = kubectl(
            unit,
            *cmd,
            check=True,
        )
        return result.stdout
    except ShellError as exc:
        raise ClusterError(f"Failed to retrieve nodes: {exc}") from exc


def get_pods(unit: Unit, namespace: str = "", wide: bool = False, output_format: str = "") -> str:
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
        cmd = ["get", "pods"]

        if not namespace:
            cmd.append("-A")
        else:
            cmd.extend(["-n", namespace])

        if wide:
            cmd.extend(["-o", "wide"])
        elif output_format:
            cmd.extend(["-o", output_format])

        result = kubectl(
            unit,
            *cmd,
            check=True,
        )
        return result.stdout
    except ShellError as exc:
        raise ClusterError(f"Failed to retrieve pods: {exc}") from exc


def get_pod_data_json(unit: Unit, namespace: str = "") -> list[dict[str, Any]]:
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
        result = get_pods(unit, namespace=namespace, output_format="json")
        data = json.loads(result)
        items: list[dict[str, Any]] = data.get("items", [])
        return items
    except json.JSONDecodeError as exc:
        raise ClusterError(f"Failed to retrieve pods data: {exc}") from exc


def describe_nodes(unit: Unit) -> str:
    """
    Get detailed node descriptions.

    Returns:
        Node descriptions as string

    Raises:
        ClusterError: If descriptions cannot be retrieved
    """
    try:
        result = kubectl(
            unit,
            "describe",
            "nodes",
            check=True,
        )
        return result.stdout
    except ShellError as exc:
        raise ClusterError(f"Failed to describe nodes: {exc}") from exc


def get_events(unit: Unit, namespace: str = "", all_namespaces: bool = True) -> str:
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
        cmd = ["get", "events"]
        if all_namespaces:
            cmd.append("-A")
        elif namespace:
            cmd.extend(["-n", namespace])

        result = kubectl(
            unit,
            *cmd,
            check=True,
        )
        return result.stdout
    except ShellError as exc:
        raise ClusterError(f"Failed to retrieve events: {exc}") from exc


def get_pod_logs(unit: Unit, namespace: str, pod_name: str, tail: int = 100) -> str:
    """
    Get logs from a specific pod.

    Args:
        namespace: Kubernetes namespace
        pod_name: Pod name
        tail: Number of lines to retrieve from end of logs

    Returns:
        Pod logs as string. Returns empty string if pod has no logs.
    """
    result = kubectl(
        unit,
        "logs",
        "-n",
        namespace,
        pod_name,
        f"--tail={tail}",
        check=False,
    )
    # Non-zero exit is OK if pod has no logs; return empty
    return result.stdout if result.returncode == 0 else ""


def create(
    unit: Unit,
    *args: str,
    dry_run: bool = False,
    output_format: str = "yaml",
    file: None | str | Path = None,
) -> Any:
    """
    Create a Kubernetes resource using kubectl.

    Args:
        unit: Unit on which to run kubectl
        *args: kubectl arguments for the resource to create (e.g. "deployment")
        dry_run: If True, perform a dry-run creation (default: False)
        output_format: Output format for dry-run (json, yaml, etc.)
        file: Optional path to a file containing the resource definition

    Returns:
        Parsed output if output_format is specified, otherwise raw stdout

    Raises:
        ClusterError: If resource creation fails
    """
    cmd = ["create", *args]
    if dry_run:
        cmd.extend(["--dry-run=client"])
    if output_format:
        cmd.extend(["-o", output_format])
    if file:
        remote = f"/tmp/kube-galaxy-create-{Path(file).stem}.yaml"
        unit.put(Path(file), remote)
        cmd.extend(["-f", remote])
    result = kubectl(unit, *cmd, check=True)
    if output_format == "json":
        return json.loads(result.stdout)
    elif output_format in ("yaml", "yml"):
        return yaml.safe_load_all(result.stdout)
    return result.stdout


def create_namespace(unit: Unit, name: str, labels: dict[str, str] | None = None) -> None:
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
        create(unit, "namespace", name)

        if labels:
            label_strs = [f"{k}={v}" for k, v in labels.items()]
            kubectl(
                unit,
                "label",
                "namespace",
                name,
                *label_strs,
                check=True,
            )
            success(f"Namespace created with labels: {name}")
        else:
            success(f"Namespace created: {name}")

    except ShellError as exc:
        raise ClusterError(f"Failed to create namespace {name}: {exc}") from exc


def delete_namespace(unit: Unit, name: str, timeout: int = 60) -> None:
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
        kubectl(
            unit,
            "delete",
            "namespace",
            name,
            "--timeout",
            f"{timeout}s",
            check=True,
        )
        success(f"Namespace deleted: {name}")
    except ShellError as exc:
        # Don't fail if namespace doesn't exist
        if "not found" in str(exc).lower():
            warning(f"Namespace {name} not found (may already be deleted)")
        else:
            raise ClusterError(f"Failed to delete namespace {name}: {exc}") from exc


def apply_manifest(unit: Unit, manifest_path: Path | str) -> None:
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

    remote = f"/tmp/kube-galaxy-apply-{manifest_path.stem}.yaml"
    try:
        info(f"Applying manifest: {manifest_path.name}")
        unit.put(manifest_path, remote)
        kubectl(unit, "apply", "-f", remote, check=True)
        success(f"Manifest applied: {manifest_path.name}")
    except ShellError as exc:
        raise ClusterError(f"Failed to apply manifest {manifest_path}: {exc}") from exc
