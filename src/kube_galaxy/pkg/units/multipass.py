"""MultipassUnit  executes operations inside a Multipass VM."""

import subprocess
from pathlib import Path

from kube_galaxy.pkg.manifest.models import NodeRole
from kube_galaxy.pkg.units._base import RunResult, Unit, UnitProvider
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.shell import ShellError, check_version


def print_dependency_status() -> None:
    """Verify that ``multipass`` is available.

    Raises:
        ComponentError: If ``multipass`` is not found.
    """
    try:
        info("Verifying multipass...")
        check_version("multipass")
    except ShellError as exc:
        raise ComponentError("MultipassUnit prerequisite not met: 'multipass' not found") from exc


class MultipassUnit(Unit):
    """Unit backed by a Multipass VM.

    All commands run as root inside the VM so ``privileged=True`` is ignored.
    """

    def __init__(self, vm_name: str, role: NodeRole, index: int) -> None:
        super().__init__(role, index)
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


class MultipassUnitProvider(UnitProvider):
    """Provisions and destroys Multipass VMs."""

    @property
    def is_ephemeral(self) -> bool:
        return True

    def provision(self, role: NodeRole, index: int) -> Unit:
        name = f"kube-galaxy-{role.value}-{index}"
        info(f"Provisioning Multipass VM '{name}' with image '{self._image}'...")
        result = subprocess.run(
            ["multipass", "launch", self._image, "--name", name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(f"Failed to launch Multipass VM '{name}': {result.stderr}")
        unit: Unit = MultipassUnit(name, role, index)
        self._track(unit)
        return unit

    def locate(self, role: NodeRole, index: int) -> Unit:
        name = f"kube-galaxy-{role.value}-{index}"
        unit: Unit = MultipassUnit(name, role, index)
        self._track(unit)
        return unit

    def deprovision(self, unit: Unit) -> None:
        info(f"Deprovisioning Multipass VM '{unit.name}'...")
        subprocess.run(
            ["multipass", "delete", "--purge", unit.name],
            capture_output=True,
            check=False,
        )
        self._untrack(unit)
