"""Abstract base for unit operations.

A ``Unit`` represents one machine (local, remote, or virtual) and exposes a
uniform interface for running commands, transferring files, and managing
per-hostname credentials.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from kube_galaxy.pkg.arch.detector import ArchInfo
from kube_galaxy.pkg.literals import SystemPaths


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

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier for this unit, e.g. ``cp-0`` or ``worker-1``."""

    @property
    @abstractmethod
    def arch(self) -> ArchInfo:
        """Architecture detected from the unit itself (e.g. via ``uname -m``)."""

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

    @abstractmethod
    def download(self, url: str, dest: str) -> None:
        """Have the unit fetch ``url`` and save it to ``dest`` on the unit."""

    @abstractmethod
    def extract(self, archive: str, dest: str) -> None:
        """Extract a tar archive at ``archive`` into directory ``dest`` on the unit."""

    @abstractmethod
    def extract_zip(self, zip_file: str, path_in_zip: str, dest: str) -> None:
        """Extract a single file from a zip archive on the unit.

        Args:
            zip_file: Path to the zip archive on the unit.
            path_in_zip: Path of the entry to extract within the zip.
            dest: Destination path on the unit for the extracted file.
        """

    @abstractmethod
    def sha256(self, path: str) -> str:
        """Return the hex SHA-256 digest of a file at ``path`` on the unit."""

    @abstractmethod
    def enlist(self, credentials: list[SiteCredential]) -> None:
        """Write per-hostname curl config files on the unit.

        Creates ``/opt/kube-galaxy/credentials/{hostname}.curlrc`` (mode 0600)
        for each credential so that ``unit.download()`` can authenticate without
        embedding tokens in process arguments.
        """

    @abstractmethod
    def release(self) -> None:
        """Remove credentials directory and clean up transient unit state."""

    @abstractmethod
    def wait_until_ready(self, timeout: float | None = None) -> None:
        """Block until the unit agent is responsive.

        Polls the unit with a simple command (``hostname``) until it exits
        successfully, or until *timeout* seconds have elapsed.

        Args:
            timeout: Maximum seconds to wait.  ``None`` uses the default
                ``Timeouts.UNIT_READY_TIMEOUT``.

        Raises:
            ClusterError: If the unit does not become ready within *timeout*.
        """

    # ------------------------------------------------------------------
    # Artifact server integration
    # ------------------------------------------------------------------

    #: Base URL of the orchestrator's artifact HTTP server.
    #: ``None`` until :meth:`set_artifact_server` is called.
    _artifact_base_url: str | None = None

    def set_artifact_server(self, base_url: str) -> None:
        """Configure the artifact server URL for this unit.

        After this call, :meth:`staging_url` returns an HTTP URL pointing to
        *base_url* instead of a local ``file://`` URL.  This allows remote
        units (LXD, Multipass, SSH) to pull artifacts from the orchestrator's
        :class:`~kube_galaxy.pkg.utils.artifact_server.ArtifactServer` via
        their normal :meth:`download` method.

        Args:
            base_url: HTTP base URL of the artifact server,
                e.g. ``"http://192.168.1.1:8765"``.
        """
        self._artifact_base_url = base_url

    def staging_url(self, local_path: Path) -> str:
        """Return a URL suitable for this unit to download a staged file.

        When an artifact server has been configured via
        :meth:`set_artifact_server`, the URL uses the HTTP scheme so that
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
        if self._artifact_base_url is not None:
            relative = local_path.relative_to(SystemPaths.staging_root())
            return f"{self._artifact_base_url.rstrip('/')}/{relative}"
        return local_path.as_uri()
