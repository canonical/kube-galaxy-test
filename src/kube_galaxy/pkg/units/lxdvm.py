"""LXDUnit  executes operations inside an LXD container or VM.

Uses only the ``lxc`` CLI  no ``pylxd`` or other Python LXD bindings.
LXD VMs run as root so the ``privileged`` flag is ignored.
"""

import subprocess
import tempfile
import time
from functools import cached_property
from pathlib import Path

from kube_galaxy.pkg.arch.detector import ArchInfo, map_to_image_arch, map_to_k8s_arch
from kube_galaxy.pkg.literals import Timeouts
from kube_galaxy.pkg.units._base import RunResult, SiteCredential, Unit
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.shell import ShellError

_CREDENTIALS_DIR = "/opt/kube-galaxy/credentials"


class LXDUnit(Unit):
    """Unit backed by an LXD container/VM.

    All commands run as root inside the container, so ``privileged=True``
    is silently accepted and has no additional effect.
    """

    def __init__(self, container_name: str) -> None:
        self._name = container_name

    @property
    def name(self) -> str:
        return self._name

    @cached_property
    def arch(self) -> ArchInfo:
        result = self._lxc_exec(["uname", "-m"])
        system = result.stdout.strip()
        return ArchInfo(
            system=system,
            k8s=map_to_k8s_arch(system),
            image=map_to_image_arch(system),
        )

    def _lxc_exec(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        """Run a command inside the LXD container via ``lxc exec``."""
        lxc_cmd: list[str] = ["lxc", "exec", self._name]
        if env:
            for k, v in env.items():
                lxc_cmd += ["--env", f"{k}={v}"]
        lxc_cmd += ["--", *cmd]
        result = subprocess.run(
            lxc_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise ShellError(lxc_cmd, result.returncode, result.stderr or "")
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
        # LXD containers run as root; privileged flag is intentionally ignored
        return self._lxc_exec(cmd, check=check, env=env, timeout=timeout)

    def put(self, local: Path, remote: str) -> None:
        result = subprocess.run(
            ["lxc", "file", "push", "--create-dirs", str(local), f"{self._name}/{remote}"],
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
            ["lxc", "file", "pull", f"{self._name}/{remote}", str(local)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to pull '{self._name}:{remote}' to '{local}': {result.stderr}"
            )

    def download(self, url: str, dest: str) -> None:
        """Download URL on the unit using curl; uses per-hostname curlrc if enlisted."""
        hostname = url.split("/")[2] if "://" in url else ""
        curlrc = f"{_CREDENTIALS_DIR}/{hostname}.curlrc"
        check_result = self._lxc_exec(["test", "-f", curlrc], check=False)
        if check_result.returncode == 0:
            cmd = ["curl", "--config", curlrc, "-fsSL", url, "-o", dest]
        else:
            cmd = ["curl", "-fsSL", url, "-o", dest]
        self._lxc_exec(["mkdir", "-p", str(Path(dest).parent)])
        self._lxc_exec(cmd, check=True)

    def extract(self, archive: str, dest: str) -> None:
        self._lxc_exec(["mkdir", "-p", dest])
        self._lxc_exec(["tar", "-xf", archive, "-C", dest])

    def extract_zip(self, zip_file: str, path_in_zip: str, dest: str) -> None:
        self._lxc_exec(["mkdir", "-p", str(Path(dest).parent)])
        self._lxc_exec(
            ["sh", "-c", f"unzip -p {zip_file} {path_in_zip} > {dest}"],
            check=True,
        )

    def sha256(self, path: str) -> str:
        result = self._lxc_exec(["sha256sum", path], check=True)
        return result.stdout.split()[0]

    def enlist(self, credentials: list[SiteCredential]) -> None:
        """Write curlrc credential files and verify unzip is available."""
        # Probe for unzip before any lifecycle stage runs
        check_unzip = self._lxc_exec(["unzip", "-v"], check=False)
        if check_unzip.returncode != 0:
            raise ComponentError(
                f"LXD unit '{self._name}' does not have 'unzip' installed. "
                "Install it before running lifecycle stages."
            )

        self._lxc_exec(["mkdir", "-p", _CREDENTIALS_DIR])
        for cred in credentials:
            content = f'header = "Authorization: {cred.auth_header}"\n'
            with tempfile.NamedTemporaryFile(mode="w", suffix=".curlrc", delete=False) as tf:
                tf.write(content)
                tmp_path = tf.name
            try:
                remote_path = f"{_CREDENTIALS_DIR}/{cred.hostname}.curlrc"
                self.put(Path(tmp_path), remote_path)
                self._lxc_exec(["chmod", "0600", remote_path])
            finally:
                Path(tmp_path).unlink(missing_ok=True)

    def release(self) -> None:
        self._lxc_exec(["rm", "-rf", _CREDENTIALS_DIR], check=False)

    def wait_until_ready(self, timeout: float | None = None) -> None:
        """Block until the LXD VM agent responds to ``hostname``.

        LXD VMs start the guest agent asynchronously after the VM boots, so
        ``lxc exec`` commands fail with exit code 255 ("VM agent isn't
        currently running") for a short window after provisioning.  This
        method polls until the agent is up or *timeout* elapses.
        """
        effective_timeout = Timeouts.UNIT_READY_TIMEOUT if timeout is None else timeout
        deadline = time.monotonic() + effective_timeout
        while True:
            result = self._lxc_exec(["hostname"], check=False)
            if result.returncode == 0:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClusterError(
                    f"Timed out waiting for LXD unit '{self._name}' to become ready "
                    f"after {effective_timeout:.0f}s"
                )
            time.sleep(min(Timeouts.UNIT_READY_INTERVAL, remaining))
