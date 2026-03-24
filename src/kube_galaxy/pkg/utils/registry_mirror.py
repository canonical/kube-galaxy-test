"""Local Docker registry mirror for the kube-galaxy orchestrator.

The orchestrator runs a plain ``registry:2`` container (no pull-through
proxy) and **skopeo** populates it before cluster nodes start pulling.
Using skopeo's ``--all`` flag copies the full multi-architecture manifest
list in a single operation without involving the local Docker daemon —
critically more efficient than ``docker pull / tag / push`` round-trips.

Typical flow::

    mirror = RegistryMirror(cfg)
    mirror.start()              # called once during setup_cluster
    mirror.preload(image_refs)  # copy multi-arch images from upstream
    mirror.retag("pause:3.10", "pause:3.10-arm64")  # optional aliasing
    ...                         # cluster lifetime
    mirror.stop()               # called once during teardown_cluster
"""

import os
from pathlib import Path

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import RegistryConfig
from kube_galaxy.pkg.utils import shell
from kube_galaxy.pkg.utils.artifact_server import detect_orchestrator_ip
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import info, success
from kube_galaxy.pkg.utils.shell import ShellError

_CONTAINER_NAME = "registry-cache"
_REGISTRY_IMAGE = "registry:2"
_REQUIRED_TOOLS = ("docker", "skopeo")


def verify_prerequisites() -> None:
    """Verify that ``docker`` and ``skopeo`` are available on PATH.

    Raises:
        ClusterError: If either tool is not found.
    """
    for tool in _REQUIRED_TOOLS:
        try:
            info(f"Verifying {tool}...")
            result = shell.run(["which", tool], check=True, capture_output=True)
            success(f"Found {tool} at {result.stdout.strip()}")
        except ShellError as exc:
            raise ClusterError(f"Registry mirror prerequisite not met: '{tool}' not found") from exc


class RegistryMirror:
    """Local Docker registry running on the orchestrator.

    Wraps a plain ``registry:2`` container (no remote-proxy configuration).
    Images are loaded into it explicitly via :meth:`preload` and :meth:`retag`,
    both of which use **skopeo** to talk directly to registry HTTP APIs —
    no local Docker daemon round-trip required.

    All cached image layers are stored under :attr:`data_dir` — a
    sub-directory of
    :meth:`~kube_galaxy.pkg.literals.SystemPaths.staging_root` — so they
    survive between runs and are cleaned up by the normal staging cleanup path.

    Files written into :attr:`data_dir` are owned by the orchestrator user
    because ``docker run`` is invoked with ``--user {uid}:{gid}``, avoiding
    the need for root permissions during cleanup.

    Args:
        cfg: Registry configuration from the manifest ``artifact.registry``
            block.
    """

    def __init__(self, cfg: RegistryConfig) -> None:
        self._cfg = cfg

    @property
    def base_url(self) -> str:
        """HTTP URL of the registry cache, routable from cluster nodes."""
        return f"http://{detect_orchestrator_ip()}:{self._cfg.port}"

    @property
    def data_dir(self) -> Path:
        """Local directory where the registry stores cached image layers."""
        return SystemPaths.staging_root() / "registry" / "data"

    def start(self) -> None:
        """Start the registry container.

        Creates :attr:`data_dir` if it does not already exist, then launches
        the Docker container in the background.
        """
        verify_prerequisites()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        shell.run(
            [
                "docker",
                "run",
                "-d",
                "-p",
                f"{self._cfg.port}:5000",
                "--name",
                _CONTAINER_NAME,
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-v",
                f"{self.data_dir}:/var/lib/registry",
                _REGISTRY_IMAGE,
            ]
        )

    def stop(self) -> None:
        """Stop and remove the registry container.

        Uses ``check=False`` so that a missing or already-stopped container
        does not raise an error during cleanup.
        """
        shell.run(["docker", "rm", "-f", _CONTAINER_NAME], check=False)

    def preload(self, image_refs: list[str | tuple[str, str]]) -> None:
        """Copy *image_refs* into the local cache.

        Each entry is either:

        * A plain registry reference string such as
          ``"registry.k8s.io/pause:3.10"``.  Only refs whose hostname matches
          ``cfg.remote_registry`` are copied; all others are silently skipped.
          The destination path is derived by stripping the registry prefix.

        * A ``(skopeo_src, local_dest_path)`` tuple for any skopeo source
          transport, including tar archives::

              ("docker-archive:/path/etcd.tar", "etcd:3.5.0")
              ("oci-archive:/path/pause.tar:pause:3.10", "pause:3.10")

          The destination is always the local registry at *local_dest_path*.

        Args:
            image_refs: Registry refs and/or ``(skopeo_src, dest_path)`` pairs.
        """
        prefix = self._cfg.remote_registry + "/"
        registry_addr = self.base_url.removeprefix("http://")
        for ref in image_refs:
            if isinstance(ref, tuple):
                src, image_path = ref
            else:
                if not ref.startswith(prefix):
                    continue
                src, image_path = f"docker://{ref}", ref[len(prefix) :]
            self._skopeo_copy(src, f"docker://{registry_addr}/{image_path}")

    def retag(self, src_path: str, dst_path: str) -> None:
        """Copy an image already in the local cache under a new tag or path.

        Both *src_path* and *dst_path* are image paths relative to the local
        registry (i.e. without the remote-registry prefix).  Useful for
        creating platform-specific tag aliases, e.g.::

            mirror.retag("pause:3.10", "pause:3.10-arm64")

        Args:
            src_path: Source image path within the local registry.
            dst_path: Destination image path within the local registry.
        """
        registry_addr = self.base_url.removeprefix("http://")
        self._skopeo_copy(
            f"docker://{registry_addr}/{src_path}",
            f"docker://{registry_addr}/{dst_path}",
            src_tls_verify=False,
        )

    def _skopeo_copy(self, src: str, dst: str, *, src_tls_verify: bool = True) -> None:
        """Run ``skopeo copy --all`` copying all platforms in one operation.

        Args:
            src: Source image transport reference (e.g. ``docker://...``).
            dst: Destination image transport reference.
            src_tls_verify: When ``False``, passes ``--src-tls-verify=false``
                (needed when the source is the local plain-HTTP registry).
        """
        cmd = ["skopeo", "copy", "--all"]
        if not src_tls_verify:
            cmd.append("--src-tls-verify=false")
        cmd += ["--dest-tls-verify=false", src, dst]
        shell.run(cmd)
