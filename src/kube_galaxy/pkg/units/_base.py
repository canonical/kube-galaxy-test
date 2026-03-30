"""Abstract base for unit operations.

A ``Unit`` represents one machine (local, remote, or virtual) and exposes a
uniform interface for running commands, transferring files, and managing
per-hostname credentials.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

from kube_galaxy.pkg.literals import SystemPaths, Timeouts, URLs
from kube_galaxy.pkg.manifest.models import NodeRole, NodesConfig
from kube_galaxy.pkg.utils.detector import ArchInfo, detect_ip, map_to_image_arch, map_to_k8s_arch
from kube_galaxy.pkg.utils.errors import ClusterError

_CREDENTIALS_DIR = "/opt/kube-galaxy/credentials"

if TYPE_CHECKING:
    from kube_galaxy.pkg.cluster_context import ClusterContext


@dataclass
class RunResult:
    """Result from running a command on a unit."""

    returncode: int
    stdout: str
    stderr: str


@dataclass
class SiteCredential:
    """Per-hostname credential stored as an Authorization header value.

    Used by ``Unit.enlist()`` to write curl config files that authenticate
    downloads without passing tokens through process arguments.
    """

    hostname: str  # e.g. "github.com", "launchpad.net"
    auth_header: str  # e.g. "Bearer ghp_xxx" or "Basic base64xxx"


class Unit(ABC):
    """Abstract representation of one machine.

    Concrete implementations:
    - ``LocalUnit``      wraps existing ``shell.run()``; backward-compat null object
    - ``LXDUnit``        ``lxc exec`` / ``lxc file push/pull``; ephemeral
    - ``SSHUnit``        ``ssh``/``scp``; pre-existing host
    - ``MultipassUnit``  ``multipass exec`` / ``multipass transfer``; ephemeral
    """

    ENLIST_TIMEOUT = Timeouts.UNIT_READY_TIMEOUT

    def __init__(self, role: NodeRole, index: int) -> None:
        self.role = role
        self.index = index
        self._ctx: ClusterContext | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier for this unit, e.g. ``cp-0`` or ``worker-1``."""

    @cached_property
    def arch(self) -> ArchInfo:
        result = self.run(["uname", "-m"])
        system = result.stdout.strip()
        return ArchInfo(
            system=system,
            k8s=map_to_k8s_arch(system),
            image=map_to_image_arch(system),
        )

    def path_exists(self, path: str | Path) -> bool:
        """Return True if a file or directory exists at the given path on the unit."""
        result = self.run(["test", "-e", str(path)], check=False)
        return result.returncode == 0

    @abstractmethod
    def run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        privileged: bool = False,
        timeout: float | None = None,
    ) -> RunResult:
        """Run a command on the unit and return its result.

        Args:
            cmd: Command and arguments as a list (no ``sudo`` prefix).
            check: Raise on non-zero exit code.
            env: Optional environment overrides.
            privileged: Command requires elevated privileges.
                        ``LocalUnit`` prepends ``sudo`` when not running as root.
                        Remote units (LXD, Multipass) run as root and ignore this.
            timeout: Optional timeout in seconds.
        """

    @abstractmethod
    def put(self, local: Path, remote: str) -> None:
        """Push a local file to the unit at ``remote`` path."""

    @abstractmethod
    def get(self, remote: str, local: Path) -> None:
        """Pull a file at ``remote`` path from the unit to ``local``."""

    def download(self, url: str, dest: str) -> None:
        """Have the unit fetch ``url`` and save it to ``dest`` on the unit."""
        self.run(["mkdir", "-p", str(Path(dest).parent)])
        self.run(["curl", "-fsSL", url, "-o", dest])

    def extract(self, archive: str, dest: str) -> None:
        """Extract a tar archive at ``archive`` into directory ``dest`` on the unit."""
        self.run(["mkdir", "-p", dest])
        self.run(["tar", "-xf", archive, "-C", dest])

    def extract_zip(self, zip_file: str, path_in_zip: str, dest: str) -> None:
        """Extract a single file from a zip archive on the unit.

        Args:
            zip_file: Path to the zip archive on the unit.
            path_in_zip: Path of the entry to extract within the zip.
            dest: Destination path on the unit for the extracted file.
        """
        self.run(["mkdir", "-p", str(Path(dest).parent)])
        self.run(["sh", "-c", f"unzip -p {zip_file} {path_in_zip} > {dest}"])

    def sha256(self, path: str) -> str:
        """Return the hex SHA-256 digest of a file at ``path`` on the unit."""
        return self.run(["sha256sum", path]).stdout.split()[0]

    def update_etc_hosts(self) -> None:
        """Ensure the unit's /etc/hosts contains entries for the orchestrator.

        Each unit's /etc/hosts is updated with entries for the orchestrator's
        hostname and IP address, both pointing to the orchestrator's IP.
        """
        if self.path_exists("/etc/hosts"):
            hosts_path = "/etc/hosts"
        else:
            # Some minimal images (e.g. Ubuntu cloud images) may not have /etc/hosts
            hosts_path = "/etc/hosts.new"
        orchestrator_ip = detect_ip()
        self.run(
            [
                "sh",
                "-c",
                f"echo '{orchestrator_ip} {URLs.ORCHESTRATOR_HOST}' >> {hosts_path}",
            ],
            privileged=True,
        )
        if hosts_path == "/etc/hosts.new":
            self.run(["mv", hosts_path, "/etc/hosts"], privileged=True)

    @cached_property
    def hostname(self) -> str:
        """Return the unit's hostname."""
        result = self.run(["hostname"], check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    def enlist(self, timeout: float | None = None) -> None:
        """Block until the unit agent is responsive.

        Polls the unit with a simple command (``hostname``) until it exits
        successfully, or until *timeout* seconds have elapsed.

        Args:
            timeout: Maximum seconds to wait.  ``None`` uses the default
                ``Timeouts.UNIT_READY_TIMEOUT``.

        Raises:
            ClusterError: If the unit does not become ready within *timeout*.
        """
        effective_timeout = Timeouts.UNIT_READY_TIMEOUT if timeout is None else timeout
        deadline = time.monotonic() + effective_timeout
        while not self.run(["hostname"], check=False).returncode == 0:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClusterError(
                    f"Timed out waiting for unit '{self.name}' to become ready "
                    f"after {effective_timeout:.0f}s"
                )
            time.sleep(min(Timeouts.UNIT_READY_INTERVAL, remaining))
        self.update_etc_hosts()

    def set_cluster_context(self, cxt: ClusterContext) -> None:
        """Configure the artifact server URL for this unit.

        After this call, :meth:`staging_url` returns an HTTP URL pointing to
        *base_url* instead of a local ``file://`` URL.  This allows remote
        units (LXD, Multipass, SSH) to pull artifacts from the orchestrator's
        :class:`~kube_galaxy.pkg.utils.artifact_server.ArtifactServer` via
        their normal :meth:`download` method.

        Args:
            ctx: Cluster context containing the HTTP base URL of the artifact server,
                e.g. ``"http://192.168.1.1:8765"``.
        """
        self._ctx = cxt

    def staging_url(self, local_path: Path) -> str:
        """Return a URL suitable for this unit to download a staged file.

        When a cluster context has been configured via
        :meth:`set_cluster_context`, the URL uses the HTTP scheme so that
        remote units can pull the file from the orchestrator.  Otherwise
        a ``file://`` URL is returned, which works for
        :class:`~kube_galaxy.pkg.units.local.LocalUnit` whose
        :meth:`download` delegates to :func:`urllib.request.urlopen`.

        Args:
            local_path: Absolute path to a file inside
                ``SystemPaths.staging_root()`` on the orchestrator.

        Returns:
            A URL string that this unit can pass to :meth:`download`.
        """
        if self._ctx is not None and self._ctx.artifact_server is not None:
            relative = local_path.relative_to(SystemPaths.staging_root())
            return f"{self._ctx.artifact_server.base_url.rstrip('/')}/{relative}"
        return local_path.as_uri()


class UnitProvider(ABC):
    """Owns the machine lifecycle  provisioning and deprovisioning."""

    def __init__(self, node_cfg: NodesConfig, image: str) -> None:
        self._image = image
        self._units: list[Unit] = []
        self._node_cfg = node_cfg

    def _track(self, unit: Unit) -> None:
        """Add *unit* to the tracked set if not already present."""
        if not any(u.name == unit.name for u in self._units):
            self._units.append(unit)

    def _untrack(self, unit: Unit) -> None:
        """Remove *unit* from the tracked set."""
        self._units = [u for u in self._units if u.name != unit.name]

    @property
    @abstractmethod
    def is_ephemeral(self) -> bool:
        """True if this provider creates and destroys machines (LXD, Multipass).

        Ephemeral providers skip component-level teardown hooks and call
        ``deprovision_all()`` directly for near-instant cleanup.
        Non-ephemeral providers (SSH, local) run full teardown per-unit.
        """

    @abstractmethod
    def provision(self, role: NodeRole, index: int) -> Unit:
        """Provision a new machine for the given role and index."""

    @abstractmethod
    def locate(self, role: NodeRole, index: int) -> Unit:
        """Return a Unit referencing an already-provisioned machine.

        Unlike ``provision``, this must not create or launch any infrastructure.
        It is used during teardown to reattach to machines that were created
        during a prior ``provision`` call.

        Args:
            role: Node role (control-plane or worker).
            index: Zero-based index within that role.

        Returns:
            A Unit pointing at the existing machine.
        """

    @abstractmethod
    def deprovision(self, unit: Unit) -> None:
        """Deprovision a single unit (destroy VM or no-op for pre-existing hosts)."""

    def locate_all(self) -> list[Unit]:
        """Return Units for all machines defined in the manifest, without provisioning."""
        ranges = {
            NodeRole.CONTROL_PLANE: self._node_cfg.control_plane,
            NodeRole.WORKER: self._node_cfg.worker,
        }
        for role in NodeRole:
            for index in range(ranges[role]):
                self._track(self.locate(role, index))
        return self._units

    def provision_all(self) -> list[Unit]:
        """Provision machines for all roles and indices defined in the manifest."""
        ranges = {
            NodeRole.CONTROL_PLANE: self._node_cfg.control_plane,
            NodeRole.WORKER: self._node_cfg.worker,
        }
        for role in NodeRole:
            for index in range(ranges[role]):
                self._track(self.provision(role, index))
        return self._units

    def deprovision_all(self) -> None:
        """Deprovision all tracked units."""
        for unit in list(self._units):
            self.deprovision(unit)
