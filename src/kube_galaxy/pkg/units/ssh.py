"""SSHUnit  executes operations on a pre-existing host via SSH/SCP."""

import subprocess
from functools import cached_property
from pathlib import Path

from kube_galaxy.pkg.arch.detector import ArchInfo, map_to_image_arch, map_to_k8s_arch
from kube_galaxy.pkg.units._base import RunResult, SiteCredential, Unit
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.shell import ShellError

_CREDENTIALS_DIR = "/opt/kube-galaxy/credentials"


class SSHUnit(Unit):
    """Unit backed by a pre-existing SSH host.

    The connecting user must be root or have passwordless sudo for privileged
    operations.  Validate this eagerly in ``SSHUnitProvider.provision()``
    before any lifecycle stage runs.
    """

    def __init__(self, host: str, unit_name: str) -> None:
        """
        Args:
            host: SSH connection string, e.g. ``ubuntu@10.0.0.10``.
            unit_name: Stable identifier for this unit, e.g. ``worker-0``.
        """
        self._host = host
        self._unit_name = unit_name

    @property
    def name(self) -> str:
        return self._unit_name

    @cached_property
    def arch(self) -> ArchInfo:
        result = self._ssh_run(["uname", "-m"])
        system = result.stdout.strip()
        return ArchInfo(
            system=system,
            k8s=map_to_k8s_arch(system),
            image=map_to_image_arch(system),
        )

    def _ssh_run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        env_prefix = " ".join(f"{k}={v}" for k, v in (env or {}).items())
        remote_cmd = (f"{env_prefix} " if env_prefix else "") + subprocess.list2cmdline(cmd)
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", self._host, remote_cmd]
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise ShellError(ssh_cmd, result.returncode, result.stderr or "")
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
        # SSHUnit requires connecting user to be root; privileged flag is no-op
        return self._ssh_run(cmd, check=check, env=env, timeout=timeout)

    def put(self, local: Path, remote: str) -> None:
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", str(local), f"{self._host}:{remote}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to scp {local} to {self._host}:{remote}: {result.stderr}"
            )

    def get(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", f"{self._host}:{remote}", str(local)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to scp {self._host}:{remote} to {local}: {result.stderr}"
            )

    def download(self, url: str, dest: str) -> None:
        hostname = url.split("/")[2] if "://" in url else ""
        curlrc = f"{_CREDENTIALS_DIR}/{hostname}.curlrc"
        check_result = self._ssh_run(["test", "-f", curlrc], check=False)
        if check_result.returncode == 0:
            cmd = ["curl", "--config", curlrc, "-fsSL", url, "-o", dest]
        else:
            cmd = ["curl", "-fsSL", url, "-o", dest]
        self._ssh_run(["mkdir", "-p", str(Path(dest).parent)])
        self._ssh_run(cmd, check=True)

    def extract(self, archive: str, dest: str) -> None:
        self._ssh_run(["mkdir", "-p", dest])
        self._ssh_run(["tar", "-xf", archive, "-C", dest])

    def extract_zip(self, zip_file: str, path_in_zip: str, dest: str) -> None:
        self._ssh_run(["mkdir", "-p", str(Path(dest).parent)])
        self._ssh_run(
            ["sh", "-c", f"unzip -p {zip_file} {path_in_zip} > {dest}"],
            check=True,
        )

    def sha256(self, path: str) -> str:
        result = self._ssh_run(["sha256sum", path], check=True)
        return result.stdout.split()[0]

    def enlist(self, credentials: list[SiteCredential]) -> None:
        import tempfile  # noqa: PLC0415

        self._ssh_run(["mkdir", "-p", _CREDENTIALS_DIR])
        for cred in credentials:
            content = f'header = "Authorization: {cred.auth_header}"\n'
            with tempfile.NamedTemporaryFile(mode="w", suffix=".curlrc", delete=False) as tf:
                tf.write(content)
                tmp_path = tf.name
            try:
                remote_path = f"{_CREDENTIALS_DIR}/{cred.hostname}.curlrc"
                self.put(Path(tmp_path), remote_path)
                self._ssh_run(["chmod", "0600", remote_path])
            finally:
                Path(tmp_path).unlink(missing_ok=True)

    def release(self) -> None:
        self._ssh_run(["rm", "-rf", _CREDENTIALS_DIR], check=False)
