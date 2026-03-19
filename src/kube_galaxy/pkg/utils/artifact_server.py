"""Static HTTP artifact server for distributing staged binaries to nodes.

The orchestrator downloads component artifacts into ``staging_root()``
(``cwd()/tmp``) during the DOWNLOAD phase.  This module exposes those
files to cluster nodes via a lightweight, read-only HTTP server so that
nodes can pull their own artifacts instead of having the orchestrator push
them.

Usage
-----
::

    from kube_galaxy.pkg.utils.artifact_server import ArtifactServer

    with ArtifactServer() as server:
        # server.base_url → "http://192.168.1.100:8765"
        unit.set_artifact_server(server.base_url)
        ...  # install phase: nodes fetch from server
    # server shuts down automatically

The server binds to ``0.0.0.0`` (all interfaces) on the specified *port*
so that VMs on any LXD/Multipass/SSH-reachable network can connect.  The
*advertise_host* parameter controls the hostname or IP address that appears
in :attr:`base_url`; it defaults to the machine's primary hostname.
"""

import http.server
import socket
import threading
from pathlib import Path
from types import TracebackType
from typing import Any

from kube_galaxy.pkg.literals import SystemPaths


class _StagingHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """Request handler that silently serves files from ``staging_root()``.

    The ``directory`` kwarg locks the handler to the staging root, so
    callers cannot traverse above that directory via ``..`` segments.
    """

    def __init__(self, *args: Any, staging_root: Path, **kwargs: Any) -> None:
        # SimpleHTTPRequestHandler accepts a ``directory`` keyword
        super().__init__(*args, directory=str(staging_root), **kwargs)

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default per-request console output."""


class ArtifactServer:
    """Read-only HTTP server that serves the orchestrator's staging area.

    The server is bound to ``0.0.0.0`` so that remote units (LXD containers,
    Multipass VMs, SSH hosts) can reach it via the orchestrator's IP address.

    Args:
        port: TCP port to listen on.  Defaults to ``8765``.
        advertise_host: Hostname or IP address included in :attr:`base_url`.
            When *None* (default), ``socket.getfqdn()`` is used.

    Example::

        with ArtifactServer(port=9000) as srv:
            print(srv.base_url)   # "http://myhost:9000"
    """

    def __init__(
        self,
        port: int = 8765,
        advertise_host: str | None = None,
    ) -> None:
        self._port = port
        self._advertise_host = advertise_host or socket.getfqdn()
        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        """HTTP base URL that remote units can use to reach this server."""
        return f"http://{self._advertise_host}:{self._port}"

    def start(self) -> None:
        """Start the HTTP server in a background daemon thread."""
        staging_root = SystemPaths.staging_root()

        def handler_factory(*args: object, **kwargs: object) -> _StagingHTTPHandler:
            return _StagingHTTPHandler(*args, staging_root=staging_root, **kwargs)

        self._server = http.server.HTTPServer(("0.0.0.0", self._port), handler_factory)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="kube-galaxy-artifact-server",
        )
        self._thread.start()

    def stop(self) -> None:
        """Shut down the HTTP server and wait for the background thread to exit."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "ArtifactServer":
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    def url_for(self, local_path: Path) -> str:
        """Return the HTTP URL at which *local_path* is accessible.

        *local_path* must be inside ``staging_root()``.  The URL is formed
        by stripping the ``staging_root()`` prefix from *local_path* and
        appending the remainder to :attr:`base_url`.

        Args:
            local_path: Absolute path inside ``staging_root()``.

        Returns:
            Full HTTP URL, e.g.
            ``"http://192.168.1.1:8765/opt/kube-galaxy/containerd/temp/containerd.tgz"``.

        Raises:
            ValueError: If *local_path* is not inside ``staging_root()``.
        """
        staging_root = SystemPaths.staging_root()
        try:
            relative = local_path.relative_to(staging_root)
        except ValueError as exc:
            raise ValueError(
                f"Path {local_path!r} is not inside staging_root {staging_root!r}"
            ) from exc
        return f"{self.base_url}/{relative}"
