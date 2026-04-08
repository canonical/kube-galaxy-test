"""KindUnit — executes operations inside kind (Kubernetes in Docker) container nodes.

Uses ``docker exec`` for running commands and ``docker cp`` for file transfers.
Kind containers run as root so the ``privileged`` flag is ignored.

The ``KindUnitProvider`` generates a kind cluster configuration from the
manifest's node counts and delegates provisioning to ``kind create cluster``.
It supports configurable node images: when ``provider.image`` is unset the
default ``kindest/node:v{kubernetes_version}`` is used.
"""

import subprocess
import textwrap
from pathlib import Path

import yaml

from kube_galaxy.pkg.manifest.models import NodeRole, NodesConfig
from kube_galaxy.pkg.units._base import RunResult, Unit, UnitProvider
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.kubeconfig import host_ip
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.shell import ShellError, check_version

_CLUSTER_NAME = "kube-galaxy"


def print_dependency_status() -> None:
    """Verify that ``kind`` and ``docker`` are available.

    Raises:
        ComponentError: If either ``kind`` or ``docker`` is not found.
    """
    try:
        info("Verifying kind...")
        check_version("kind")
    except ShellError as exc:
        raise ComponentError("KindUnit prerequisite not met: 'kind' not found") from exc

    try:
        info("Verifying docker...")
        check_version("docker")
    except ShellError as exc:
        raise ComponentError("KindUnit prerequisite not met: 'docker' not found") from exc


def _container_name(cluster: str, role: NodeRole, index: int) -> str:
    """Derive the Docker container name that kind assigns to a node.

    Kind naming convention:
    - Single control-plane: ``{cluster}-control-plane``
    - Additional control-planes: ``{cluster}-control-plane2``, …
    - First worker: ``{cluster}-worker``
    - Additional workers: ``{cluster}-worker2``, …
    """
    suffix = role.value.replace("-", "")  # 'control-plane' → 'controlplane'
    # kind uses 'control-plane' in its container names, not 'controlplane'
    suffix = "control-plane" if role == NodeRole.CONTROL_PLANE else "worker"
    # First node of each role has no numeric suffix; subsequent nodes are 2, 3, …
    if index == 0:
        return f"{cluster}-{suffix}"
    return f"{cluster}-{suffix}{index + 1}"


def _build_kind_config(
    node_cfg: NodesConfig,
    image: str,
) -> str:
    """Generate a kind cluster configuration YAML.

    Args:
        node_cfg: Control-plane and worker counts from the manifest.
        image: Node image (e.g. ``kindest/node:v1.35.0``).

    Returns:
        YAML string suitable for ``kind create cluster --config``.
    """
    nodes: list[dict[str, str]] = []
    for _ in range(node_cfg.control_plane):
        node: dict[str, str] = {"role": "control-plane"}
        if image:
            node["image"] = image
        nodes.append(node)
    for _ in range(node_cfg.worker):
        node = {"role": "worker"}
        if image:
            node["image"] = image
        nodes.append(node)

    network: dict[str, str | int] = {
        "apiServerAddress": "0.0.0.0",
        "apiServerPort": 6443,
    }
    host_ip_addr = host_ip()
    kubeadm_patch = (  # noqa: UP032 — .format() intentional for readability
        "kind: ClusterConfiguration\n"
        "apiServer:\n"
        "  certSANs:\n"
        '  - "{}"\n'
        '  - "127.0.0.1"\n'
        '  - "localhost"\n'
        '  - "0.0.0.0"\n'
    ).format(host_ip_addr)
    config = {
        "kind": "Cluster",
        "apiVersion": "kind.x-k8s.io/v1alpha4",
        "networking": network,
        "nodes": nodes,
        "kubeadmConfigPatches": [kubeadm_patch],
    }
    return yaml.safe_dump(config, default_flow_style=False)


class KindUnit(Unit):
    """Unit backed by a kind (Docker) container node.

    All commands run as root inside the container, so ``privileged=True``
    is silently accepted and has no additional effect.
    """

    def __init__(self, container_name: str, role: NodeRole, index: int) -> None:
        super().__init__(role, index)
        self._name = container_name

    @property
    def name(self) -> str:
        return self._name

    def _docker_exec(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        """Run a command inside the kind container via ``docker exec``."""
        docker_cmd: list[str] = ["docker", "exec"]
        if env:
            for k, v in env.items():
                docker_cmd += ["-e", f"{k}={v}"]
        docker_cmd += [self._name, *cmd]
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise ShellError(docker_cmd, result.returncode, result.stderr or "")
        return RunResult(
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

    def run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        privileged: bool = False,
        timeout: float | None = None,
    ) -> RunResult:
        # Kind containers run as root; privileged flag is intentionally ignored
        return self._docker_exec(cmd, check=check, env=env, timeout=timeout)

    def put(self, local: Path, remote: str) -> None:
        # Ensure target directory exists inside the container
        self._docker_exec(["mkdir", "-p", str(Path(remote).parent)], check=False)
        result = subprocess.run(
            ["docker", "cp", str(local), f"{self._name}:{remote}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to push '{local}' to '{self._name}:{remote}': {result.stderr}"
            )

    def get(self, remote: str, local: Path) -> None:
        ensure_dir(local.parent)
        result = subprocess.run(
            ["docker", "cp", f"{self._name}:{remote}", str(local)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to pull '{self._name}:{remote}' to '{local}': {result.stderr}"
            )


class KindUnitProvider(UnitProvider):
    """Provisions and destroys kind (Kubernetes in Docker) clusters.

    Unlike LXD/Multipass providers that manage individual VMs, the
    ``KindUnitProvider`` creates an entire kind cluster with a single
    ``kind create cluster`` command.  Individual nodes are accessed via
    ``docker exec`` into the named containers.

    Args:
        node_cfg: Control-plane and worker counts from the manifest.
        image: Node image.  When empty, kind uses its built-in default
            (``kindest/node`` matching the ``kind`` binary version).
        cluster_name: Name for the kind cluster (default: ``kube-galaxy``).
    """

    def __init__(
        self,
        node_cfg: NodesConfig,
        image: str,
        cluster_name: str = _CLUSTER_NAME,
    ) -> None:
        super().__init__(node_cfg, image)
        self._cluster_name = cluster_name
        self._provisioned = False

    @property
    def is_ephemeral(self) -> bool:
        return True

    def _ensure_cluster(self) -> None:
        """Create the kind cluster if it hasn't been created yet.

        Kind provisions all nodes in a single ``kind create cluster`` call,
        so this is invoked lazily on the first ``provision()`` call only.
        """
        if self._provisioned:
            return

        config_yaml = _build_kind_config(self._node_cfg, self._image)
        info(f"Creating kind cluster '{self._cluster_name}'...")
        info(f"Kind config:\n{textwrap.indent(config_yaml, '  ')}")

        # Write config to a temporary file
        config_path = Path(f"/tmp/kind-config-{self._cluster_name}.yaml")
        config_path.write_text(config_yaml)

        cmd = [
            "kind",
            "create",
            "cluster",
            f"--name={self._cluster_name}",
            f"--config={config_path}",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to create kind cluster '{self._cluster_name}': {result.stderr}"
            )
        self._provisioned = True
        info(f"Kind cluster '{self._cluster_name}' created successfully")

    def provision(self, role: NodeRole, index: int) -> Unit:
        self._ensure_cluster()
        name = _container_name(self._cluster_name, role, index)
        info(f"Attaching to kind node '{name}' ({role.value}-{index})")
        return KindUnit(name, role, index)

    def locate(self, role: NodeRole, index: int) -> Unit:
        name = _container_name(self._cluster_name, role, index)
        return KindUnit(name, role, index)

    def deprovision(self, unit: Unit) -> None:
        # Kind manages all nodes as a cluster; individual node removal is not
        # supported.  Actual cleanup happens in deprovision_all().
        self._untrack(unit)

    def deprovision_all(self) -> None:
        """Delete the entire kind cluster."""
        info(f"Deleting kind cluster '{self._cluster_name}'...")
        result = subprocess.run(
            ["kind", "delete", "cluster", f"--name={self._cluster_name}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to delete kind cluster '{self._cluster_name}': {result.stderr}"
            )
        self._units.clear()
        self._provisioned = False
        info(f"Kind cluster '{self._cluster_name}' deleted")
