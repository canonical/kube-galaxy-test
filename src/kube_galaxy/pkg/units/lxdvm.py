"""LXDUnit  executes operations inside an LXD container or VM.

Uses only the ``lxc`` CLI  no ``pylxd`` or other Python LXD bindings.
LXD VMs run as root so the ``privileged`` flag is ignored.
"""

import subprocess
from pathlib import Path

from kube_galaxy.pkg.manifest.models import NodeRole
from kube_galaxy.pkg.units._base import RunResult, Unit, UnitProvider
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.shell import ShellError


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


class LXDUnitProvider(UnitProvider):
    """Provisions and destroys LXD containers/VMs."""

    def __init__(self, image: str = "ubuntu:24.04") -> None:
        super().__init__()
        self._image = image

    @property
    def is_ephemeral(self) -> bool:
        return True

    def provision(self, role: NodeRole, index: int) -> Unit:
        name = f"kube-galaxy-{role.value}-{index}"
        info(f"Provisioning LXD VM '{name}' with image '{self._image}'...")
        result = subprocess.run(
            [
                "lxc",
                "launch",
                self._image,
                name,
                "--vm",
                "-c",
                "limits.cpu=2",
                "-c",
                "limits.memory=4GB",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(f"Failed to launch LXD VM '{name}': {result.stderr}")
        unit: Unit = LXDUnit(name)
        self._track(unit)
        return unit

    def locate(self, role: NodeRole, index: int) -> Unit:
        name = f"kube-galaxy-{role.value}-{index}"
        unit: Unit = LXDUnit(name)
        self._track(unit)
        return unit

    def deprovision(self, unit: Unit) -> None:
        info(f"Deprovisioning LXD VM '{unit.name}'...")

        subprocess.run(
            ["lxc", "delete", "--force", unit.name],
            capture_output=True,
            check=False,
        )
        self._untrack(unit)
