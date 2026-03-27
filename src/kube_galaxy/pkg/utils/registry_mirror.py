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

import json
import os
from pathlib import Path

from kube_galaxy.pkg.literals import SystemPaths, URLs
from kube_galaxy.pkg.manifest.models import RegistryConfig
from kube_galaxy.pkg.utils import shell
from kube_galaxy.pkg.utils.detector import detect_ip
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.shell import ShellError

_CONTAINER_NAME = "registry-cache"
_REGISTRY_IMAGE = "registry:3"
_REQUIRED_TOOLS = ("docker", "skopeo")


def _print_dependency_status() -> None:
    """Verify that ``docker`` and ``skopeo`` are available on PATH.

    Raises:
        ClusterError: If either tool is not found.
    """
    for tool in _REQUIRED_TOOLS:
        try:
            info(f"Verifying {tool}...")
            shell.check_version(tool)
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
    def data_dir(self) -> Path:
        """Local directory where the registry stores cached image layers."""
        return SystemPaths.staging_root() / "registry" / "data"

    def start(self) -> None:
        """Start the registry container.

        Creates :attr:`data_dir` if it does not already exist, then launches
        the Docker container in the background.
        """
        _print_dependency_status()
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

    def stop(self, force: bool = False) -> None:
        """Stop and remove the registry container.

        Args:
            force: If ``True``, does not raise an error if the container is not
                   found or fails to stop; otherwise, any such error is raised.
        """
        shell.run(["docker", "rm", "-f", _CONTAINER_NAME], check=not force)

    def inspect(self, image_ref: str) -> str:
        """Return the image name embedded in a skopeo source reference.

        Runs ``skopeo inspect`` against *image_ref* (e.g.
        ``"docker-archive:/path/image.tar"``) and returns the ``Name`` field
        from the resulting JSON, with the registry hostname prefix stripped so
        the result is suitable as a :meth:`preload` *mirror_path*.

        Returns an empty string if the ``Name`` field is absent or blank.

        Args:
            image_ref: Any skopeo source transport reference.

        Returns:
            The image path without registry host, e.g. ``"pause:3.10"``.
        """
        result = shell.run(["skopeo", "inspect", image_ref], capture_output=True)
        name: str = json.loads(result.stdout).get("Name", "")
        if not name:
            return ""
        # Strip leading registry hostname (e.g. "registry.k8s.io/pause:3.10" -> "pause:3.10")
        return name.split("/", 1)[-1] if "/" in name else name

    def registry_address(self, local: bool = False) -> str:
        """Return the registry address for use in container image references."""
        if local:
            registry_addr = detect_ip()
            return f"{registry_addr}:{self._cfg.port}"
        return f"{URLs.ORCHESTRATOR_HOST}:{self._cfg.port}"

    def preload(self, image_ref: str, mirror_path: str) -> None:
        """Copy a single image into the local registry cache.

        *image_ref* is any skopeo source transport reference:

        * A ``docker://`` registry reference, e.g.
          ``"docker://registry.k8s.io/pause:3.10"``.
        * An archive reference, e.g.
          ``"docker-archive:/path/etcd.tar"`` or
          ``"oci-archive:/path/pause.tar:pause:3.10"``.

        *mirror_path* is the destination path within the local registry
        (without the registry host prefix), e.g. ``"pause:3.10"``.

        Args:
            image_ref: Skopeo source transport reference for the image.
            mirror_path: Destination path within the local registry.
        """
        registry_addr = self.registry_address(local=True)
        self._skopeo_copy(image_ref, f"docker://{registry_addr}/{mirror_path}")

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
        registry_addr = self.registry_address(local=True)
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
        cmd = ["skopeo", "copy", "--all", "--quiet"]
        if not src_tls_verify:
            cmd.append("--src-tls-verify=false")
        cmd += ["--dest-tls-verify=false", src, dst]
        shell.run(cmd)
