"""MultipassUnit  executes operations inside a Multipass VM."""

import subprocess
import tempfile
import time
from pathlib import Path

from kube_galaxy.pkg.literals import Timeouts
from kube_galaxy.pkg.units._base import RunResult, SiteCredential, Unit
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.shell import ShellError

_CREDENTIALS_DIR = "/opt/kube-galaxy/credentials"


class MultipassUnit(Unit):
    """Unit backed by a Multipass VM.

    All commands run as root inside the VM so ``privileged=True`` is ignored.
    """

    def __init__(self, vm_name: str) -> None:
        self._name = vm_name

    @property
    def name(self) -> str:
        return self._name

    def _mp_exec(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        mp_cmd: list[str] = ["multipass", "exec", self._name, "--"]
        if env:
            mp_cmd += [f"{k}={v}" for k, v in env.items()]
        mp_cmd += cmd
        result = subprocess.run(
            mp_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise ShellError(mp_cmd, result.returncode, result.stderr or "")
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
        # Multipass VMs run as root; privileged flag is intentionally ignored
        return self._mp_exec(cmd, check=check, env=env, timeout=timeout)

    def put(self, local: Path, remote: str) -> None:
        result = subprocess.run(
            ["multipass", "transfer", str(local), f"{self._name}:{remote}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to transfer '{local}' to '{self._name}:{remote}': {result.stderr}"
            )

    def get(self, remote: str, local: Path) -> None:
        ensure_dir(local.parent)
        result = subprocess.run(
            ["multipass", "transfer", f"{self._name}:{remote}", str(local)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to transfer '{self._name}:{remote}' to '{local}': {result.stderr}"
            )

    def download(self, url: str, dest: str) -> None:
        hostname = url.split("/")[2] if "://" in url else ""
        curlrc = f"{_CREDENTIALS_DIR}/{hostname}.curlrc"
        check_result = self._mp_exec(["test", "-f", curlrc], check=False)
        if check_result.returncode == 0:
            cmd = ["curl", "--config", curlrc, "-fsSL", url, "-o", dest]
        else:
            cmd = ["curl", "-fsSL", url, "-o", dest]
        self._mp_exec(["mkdir", "-p", str(Path(dest).parent)])
        self._mp_exec(cmd, check=True)

    def extract(self, archive: str, dest: str) -> None:
        self._mp_exec(["mkdir", "-p", dest])
        self._mp_exec(["tar", "-xf", archive, "-C", dest])

    def extract_zip(self, zip_file: str, path_in_zip: str, dest: str) -> None:
        self._mp_exec(["mkdir", "-p", str(Path(dest).parent)])
        self._mp_exec(
            ["sh", "-c", f"unzip -p {zip_file} {path_in_zip} > {dest}"],
            check=True,
        )

    def sha256(self, path: str) -> str:
        result = self._mp_exec(["sha256sum", path], check=True)
        return result.stdout.split()[0]

    def enlist(self, credentials: list[SiteCredential]) -> None:
        self._mp_exec(["mkdir", "-p", _CREDENTIALS_DIR])
        for cred in credentials:
            content = f'header = "Authorization: {cred.auth_header}"\n'
            with tempfile.NamedTemporaryFile(mode="w", suffix=".curlrc", delete=False) as tf:
                tf.write(content)
                tmp_path = tf.name
            try:
                remote_path = f"{_CREDENTIALS_DIR}/{cred.hostname}.curlrc"
                self.put(Path(tmp_path), remote_path)
                self._mp_exec(["chmod", "0600", remote_path])
            finally:
                Path(tmp_path).unlink(missing_ok=True)

    def release(self) -> None:
        self._mp_exec(["rm", "-rf", _CREDENTIALS_DIR], check=False)

    def wait_until_ready(self, timeout: float | None = None) -> None:
        """Block until the Multipass VM responds to ``hostname``."""
        effective_timeout = Timeouts.UNIT_READY_TIMEOUT if timeout is None else timeout
        deadline = time.monotonic() + effective_timeout
        while True:
            result = self._mp_exec(["hostname"], check=False)
            if result.returncode == 0:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClusterError(
                    f"Timed out waiting for Multipass unit '{self._name}' to become ready "
                    f"after {effective_timeout:.0f}s"
                )
            time.sleep(min(Timeouts.UNIT_READY_INTERVAL, remaining))
