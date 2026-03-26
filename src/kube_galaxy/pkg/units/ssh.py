"""SSHUnit  executes operations on a pre-existing host via SSH/SCP."""

import subprocess
from pathlib import Path

from kube_galaxy.pkg.manifest.models import NodeRole, NodesConfig
from kube_galaxy.pkg.units._base import RunResult, Unit, UnitProvider
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.shell import ShellError, check_installed, check_version


def print_dependency_status() -> None:
    """Verify that ``ssh`` and ``scp`` are available.

    Raises:
        ComponentError: If either ``ssh`` or ``scp`` is not found.
    """
    try:
        check_version("ssh")
        check_installed("scp")
    except ShellError as exc:
        raise ComponentError(
            "SSHUnit prerequisites not met: 'ssh' and 'scp' must be installed"
        ) from exc


class SSHUnit(Unit):
    """Unit backed by a pre-existing SSH host.

    The connecting user must be root or have passwordless sudo for privileged
    operations.  Validate this eagerly in ``SSHUnitProvider.provision()``
    before any lifecycle stage runs.
    """

    def __init__(self, host: str, role: NodeRole, index: int) -> None:
        """
        Args:
            host: SSH connection string, e.g. ``ubuntu@10.0.0.10``.
            role: Node role for this unit, used for naming and logging.
            index: Node index for this unit, used for naming and logging.
        """
        super().__init__(role, index)
        self._host = host
        self._unit_name = f"{role.value}-{index}"

    @property
    def name(self) -> str:
        return self._unit_name

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
            raise ComponentError(f"Failed to scp {local} to {self._host}:{remote}: {result.stderr}")

    def get(self, remote: str, local: Path) -> None:
        ensure_dir(local.parent)
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", f"{self._host}:{remote}", str(local)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(f"Failed to scp {self._host}:{remote} to {local}: {result.stderr}")


class SSHUnitProvider(UnitProvider):
    """Returns SSHUnit instances for pre-existing hosts; no-op deprovision."""

    def __init__(self, counts: NodesConfig, image: str, hosts: list[str]) -> None:
        super().__init__(counts, image)
        if len(hosts) < counts.control_plane + counts.worker:
            raise ValueError("Not enough hosts provided for the specified role counts.")
        elif len(hosts) > counts.control_plane + counts.worker:
            info("Warning: More hosts provided than needed; extra hosts will be ignored.")
        self._hosts = hosts

    @property
    def is_ephemeral(self) -> bool:
        return False

    def _host_index(self, role: NodeRole, index: int) -> int:
        if role == NodeRole.CONTROL_PLANE:
            return index
        elif role == NodeRole.WORKER:
            return self._counts.control_plane + index
        else:
            raise ValueError(f"Unknown role: {role}")

    def provision(self, role: NodeRole, index: int) -> Unit:
        host = self._hosts[self._host_index(role, index)]
        info(f"SSH unit '{role.value}-{index}' at host '{host}'...")
        return SSHUnit(host=host, role=role, index=index)

    # For SSHUnit, provisioning and locating are the same since units are pre-existing
    locate = provision

    def deprovision(self, unit: Unit) -> None:
        info(f"SSH host '{unit.name}' is pre-existing; skipping deprovision.")
