"""JujuUnit executes operations inside a juju machine model

Uses only the ``juju`` CLI
Juju machines run as root so the ``privileged`` flag is ignored.
"""

import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from kube_galaxy.pkg.literals import Timeouts
from kube_galaxy.pkg.manifest.models import NodeRole, NodesConfig
from kube_galaxy.pkg.units._base import RunResult, Unit, UnitProvider
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError
from kube_galaxy.pkg.utils.logging import info, warning
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.shell import ShellError, check_version, run


def print_dependency_status() -> None:
    """Verify that ``juju`` is available.

    Raises:
        ComponentError: If ``juju`` is not found.
    """
    try:
        info("Verifying juju...")
        check_version("juju")
    except ShellError as exc:
        raise ComponentError("JujuUnit prerequisite not met: 'juju' not found") from exc

    if not _get_state():
        raise ComponentError(
            "JujuUnit prerequisite not met: 'juju status' did not return valid JSON"
        )


def _get_state(name: str = "", timeout: float = 10) -> dict[str, Any]:
    cmd = f"juju status {name} --format json"
    result = run(shlex.split(cmd), check=False, capture_output=True, text=True, timeout=timeout)
    if result.returncode == 0:
        parsed = None
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            warning(f"Failed to parse juju status output as JSON: {result.stdout}")
        if isinstance(parsed, dict):
            return parsed
    return {}


def _get_application_status(app: str, timeout: float = 10) -> dict[str, Any]:
    state = _get_state(app, timeout=timeout)
    try:
        apps = state["applications"][app]
        if isinstance(apps, dict):
            return apps
    except KeyError:
        warning(f"Failed to get status for juju application '{app}': unexpected status format")
    return {}


def _get_unit_status(unit: str, timeout: float = 10) -> dict[str, Any]:
    state = _get_application_status(unit.split("/")[0], timeout=timeout)
    try:
        units = state["units"][unit]
        if isinstance(units, dict):
            return units
    except KeyError:
        warning(f"Failed to get status for juju unit '{unit}': unexpected status format")
    return {}


def _get_workload_status(unit: str, timeout: float = 10) -> tuple[str, str] | None:
    if unit_status := _get_unit_status(unit, timeout=timeout):
        try:
            workload, juju = (unit_status[_]["current"] for _ in ("workload-status", "juju-status"))
            return workload, juju
        except KeyError:
            warning(
                f"Failed to get workload status for juju unit '{unit}': unexpected status format"
            )
    return None


class JujuUnit(Unit):
    """Unit backed by a Juju machine.

    All commands run as root inside the machine, so ``privileged=True``
    is silently accepted and has no additional effect.
    """

    JUJU_PATIENT_TIMEOUT = 900  # Juju machines can be slow to provision and become ready

    def __init__(
        self, machine_name: str, role: NodeRole, index: int, tunnel_ports: list[int] | None = None
    ) -> None:
        super().__init__(role, index)
        self._name = machine_name
        self._tunnel_ports: list[int] = tunnel_ports or []
        self._tunnel: subprocess.Popen[bytes] | None = None

    @property
    def name(self) -> str:
        return self._name

    @staticmethod
    def application(unit: str) -> str:
        return unit.split("/")[0]

    def open_tunnel(self) -> None:
        """Open (or re-open) the SSH reverse tunnel for this unit.

        Idempotent: no-op if the tunnel process is already running.
        Uses ``juju ssh`` so that Juju handles host-key verification and
        identity management.
        """
        if self._tunnel is not None and self._tunnel.poll() is None:
            return  # already alive
        if not self._tunnel_ports:
            return
        cmd = ["juju", "ssh", "--no-host-key-checks", self._name, "-N"]
        for port in self._tunnel_ports:
            cmd += ["-R", f"{port}:localhost:{port}"]
        self._tunnel = subprocess.Popen(cmd)

    def stop_tunnel(self) -> None:
        """Terminate the SSH reverse tunnel if it is running."""
        if self._tunnel is not None:
            self._tunnel.terminate()
            try:
                self._tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._tunnel.kill()
            self._tunnel = None

    def tunnel_alive(self) -> bool:
        """Return True if the SSH reverse tunnel process is currently running."""
        return self._tunnel is not None and self._tunnel.poll() is None

    def _enable_root_ssh(self) -> None:
        # Juju machines don't have root SSH access by default,
        # but we can copy the ubuntu user's authorized_keys to root
        self.run(["sudo", "mkdir", "-p", "/root/.ssh"], check=True)
        self.run(
            ["sudo", "cp", "/home/ubuntu/.ssh/authorized_keys", "/root/.ssh/authorized_keys"],
            check=True,
        )

    def enlist(self, orchestrator_ip: str, timeout: float | None = None) -> None:
        # Juju machines can take a while to come up, so instead we wait for active/idle
        effective_timeout = self.JUJU_PATIENT_TIMEOUT if timeout is None else timeout
        deadline = time.monotonic() + effective_timeout
        while not _get_workload_status(self.name, timeout=10) == ("active", "idle"):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClusterError(
                    f"Timed out waiting for unit '{self.name}' to become ready "
                    f"after {effective_timeout:.0f}s"
                )
            time.sleep(min(Timeouts.UNIT_READY_INTERVAL, remaining))
        self._enable_root_ssh()
        self.open_tunnel()
        self.update_etc_hosts(orchestrator_ip)

    def _juju_exec(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        """Run a command inside the Juju machine via ``juju exec``."""
        juju_cmd: list[str] = ["juju", "exec", "--unit", self._name, "--"]
        if env:
            for k, v in env.items():
                juju_cmd.append(f"{k}={v}")
        juju_cmd.extend(cmd)
        result = subprocess.run(
            juju_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise ShellError(juju_cmd, result.returncode, result.stderr or "")
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
        # Juju machines run as root; privileged flag is intentionally ignored
        return self._juju_exec(cmd, check=check, env=env, timeout=timeout)

    def put(self, local: Path, remote: str) -> None:
        self.run(["mkdir", "-p", str(Path(remote).parent)], check=True)
        cmd = f"juju scp {local} root@{self.name}:{remote}"
        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to push '{local}' ({local.stat().st_size} bytes) "
                f"to '{self._name}:{remote}': {result.stderr}"
            )

    def get(self, remote: str, local: Path) -> None:
        ensure_dir(local.parent)
        cmd = f"juju scp root@{self._name}:{remote} {local}"
        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to pull '{self._name}:{remote}' to '{local}': {result.stderr}"
            )


class JujuUnitProvider(UnitProvider):
    """Provisions and destroys Juju machines."""

    def __init__(
        self, node_cfg: NodesConfig, image: str, tunnel_ports: list[int] | None = None
    ) -> None:
        super().__init__(node_cfg, image)
        self._tunnel_ports: list[int] = tunnel_ports or []

    def orchestrator_ip(self) -> str:
        """Return 127.0.0.1 — Juju units reach the orchestrator via reverse SSH tunnel."""
        return "127.0.0.1"

    @property
    def is_ephemeral(self) -> bool:
        return True

    def _cloud_type(self) -> str:
        cmd = ["juju", "models", "--format", "json"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(f"Failed to get juju models: {result.stderr}")
        models = json.loads(result.stdout)
        if current_model := models.get("current-model"):
            active = [m for m in models.get("models", []) if m.get("short-name") == current_model]
            model_info = active[0] if active else {}
            return str(model_info.get("type", "unknown"))
        return "unknown"

    def provision(self, role: NodeRole, index: int) -> Unit:
        application = f"kube-galaxy-{role.value}"
        info(f"Provisioning Juju machine '{application}' with image '{self._image}'...")
        cloud_type = self._cloud_type()
        if index == 0:
            virt_type = "virt-type=virtual-machine" if cloud_type in ("lxd", "microstack") else ""
            cmd = shlex.split(
                f"juju deploy ch:ubuntu {application} "
                f"--base {self._image.replace(':', '@')} "
                f"--constraints='cores=2 mem=4G {virt_type}'"
            )
        else:
            cmd = [
                "juju",
                "add-unit",
                application,
            ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to launch Juju machine '{application}' {cmd=}: {result.stderr}"
            )

        return self.locate(role, index)

    def locate(self, role: NodeRole, index: int) -> Unit:
        application = f"kube-galaxy-{role.value}"
        while not (app := _get_application_status(application)) or not app.get("units"):
            info(f"Waiting for new juju unit '{application}' to appear...")
            time.sleep(5)
        # the unit with the highest index should be the one we just launched
        unit_name = sorted(app["units"].keys())[index]
        return JujuUnit(unit_name, role, index, tunnel_ports=self._tunnel_ports)

    def open_tunnels(self) -> None:
        """Open SSH reverse tunnels for all tracked Juju units."""
        for unit in self._units:
            if isinstance(unit, JujuUnit):
                unit.open_tunnel()

    def stop_tunnels(self) -> None:
        """Close SSH reverse tunnels for all tracked Juju units."""
        for unit in self._units:
            if isinstance(unit, JujuUnit):
                unit.stop_tunnel()

    def deprovision(self, unit: Unit) -> None:
        if isinstance(unit, JujuUnit):
            unit.stop_tunnel()
        info(f"Deprovisioning Juju machine '{unit.name}'...")
        if unit.index == 0:
            cmd = ["juju", "remove-application", "--force", "--no-prompt", unit.name.split("/")[0]]
        else:
            cmd = ["juju", "remove-unit", "--force", "--no-prompt", unit.name]
        subprocess.run(
            cmd,
            capture_output=True,
            check=False,
        )
        self._untrack(unit)
