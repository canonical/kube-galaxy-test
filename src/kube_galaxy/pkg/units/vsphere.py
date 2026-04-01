"""VSphereUnit  executes operations on a vSphere VM via govc and SSH.

Uses the ``govc`` CLI (part of `govmomi <https://github.com/vmware/govmomi>`_)
for VM lifecycle management (clone, power-on, destroy) and plain ``ssh``/``scp``
for runtime operations once the VM is accessible.

vCenter credentials are expected in the standard ``GOVC_URL``,
``GOVC_USERNAME`` and ``GOVC_PASSWORD`` environment variables consumed by
``govc`` — they are never stored in the manifest.
"""

import subprocess
from pathlib import Path

from kube_galaxy.pkg.manifest.models import NodeRole, NodesConfig
from kube_galaxy.pkg.units._base import RunResult, Unit, UnitProvider
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.shell import ShellError, check_installed, check_version


def print_dependency_status() -> None:
    """Verify that ``govc``, ``ssh`` and ``scp`` are available.

    Raises:
        ComponentError: If any prerequisite is not found.
    """
    try:
        info("Verifying govc...")
        check_version("govc")
        check_version("ssh")
        check_installed("scp")
    except ShellError as exc:
        raise ComponentError(
            "VSphereUnit prerequisites not met: 'govc', 'ssh' and 'scp' must be installed"
        ) from exc


def _govc_vm_ip(vm_name: str) -> str:
    """Return the primary IP address of a vSphere VM via ``govc vm.ip``.

    Raises:
        ComponentError: If the IP cannot be retrieved.
    """
    result = subprocess.run(
        ["govc", "vm.ip", vm_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ComponentError(f"Failed to retrieve IP for vSphere VM '{vm_name}': {result.stderr}")
    ip = result.stdout.strip()
    if not ip:
        raise ComponentError(f"govc vm.ip returned empty IP for VM '{vm_name}'")
    return ip


class VSphereUnit(Unit):
    """Unit backed by a vSphere VM.

    All runtime commands are executed over SSH as root.  The ``privileged``
    flag is silently accepted and has no additional effect (same as LXD /
    Multipass units).
    """

    def __init__(self, vm_name: str, ip: str, role: NodeRole, index: int) -> None:
        super().__init__(role, index)
        self._vm_name = vm_name
        self._ip = ip

    @property
    def name(self) -> str:
        return self._vm_name

    def _ssh_run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        """Run a command on the VM via ``ssh``."""
        env_prefix = " ".join(f"{k}={v}" for k, v in (env or {}).items())
        remote_cmd = (f"{env_prefix} " if env_prefix else "") + subprocess.list2cmdline(cmd)
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"root@{self._ip}", remote_cmd]
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
        # vSphere VMs are accessed as root over SSH; privileged flag is a no-op
        return self._ssh_run(cmd, check=check, env=env, timeout=timeout)

    def put(self, local: Path, remote: str) -> None:
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", str(local), f"root@{self._ip}:{remote}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to scp '{local}' to '{self._vm_name}:{remote}': {result.stderr}"
            )

    def get(self, remote: str, local: Path) -> None:
        ensure_dir(local.parent)
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", f"root@{self._ip}:{remote}", str(local)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to scp '{self._vm_name}:{remote}' to '{local}': {result.stderr}"
            )


class VSphereUnitProvider(UnitProvider):
    """Provisions and destroys vSphere VMs via the ``govc`` CLI.

    VMs are cloned from a template image, powered on, and their IP addresses
    are retrieved via VMware Guest Tools (``govc vm.ip``).
    """

    def __init__(
        self,
        node_cfg: NodesConfig,
        image: str,
        *,
        datacenter: str = "",
        datastore: str = "",
        network: str = "",
    ) -> None:
        super().__init__(node_cfg, image)
        self._datacenter = datacenter
        self._datastore = datastore
        self._network = network

    @property
    def is_ephemeral(self) -> bool:
        return True

    def provision(self, role: NodeRole, index: int) -> Unit:
        name = f"kube-galaxy-{role.value}-{index}"
        info(f"Cloning vSphere VM '{name}' from template '{self._image}'...")
        clone_cmd: list[str] = ["govc", "vm.clone", "-vm", self._image]
        if self._datacenter:
            clone_cmd += ["-dc", self._datacenter]
        if self._datastore:
            clone_cmd += ["-ds", self._datastore]
        if self._network:
            clone_cmd += ["-net", self._network]
        clone_cmd.append(name)
        result = subprocess.run(
            clone_cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(f"Failed to clone vSphere VM '{name}': {result.stderr}")
        power_result = subprocess.run(
            ["govc", "vm.power", "-on", name],
            capture_output=True,
            text=True,
            check=False,
        )
        if power_result.returncode != 0:
            raise ComponentError(f"Failed to power on vSphere VM '{name}': {power_result.stderr}")
        ip = _govc_vm_ip(name)
        unit = VSphereUnit(name, ip, role, index)
        self._track(unit)
        return unit

    def locate(self, role: NodeRole, index: int) -> Unit:
        name = f"kube-galaxy-{role.value}-{index}"
        ip = _govc_vm_ip(name)
        unit = VSphereUnit(name, ip, role, index)
        self._track(unit)
        return unit

    def deprovision(self, unit: Unit) -> None:
        info(f"Destroying vSphere VM '{unit.name}'...")
        subprocess.run(
            ["govc", "vm.destroy", unit.name],
            capture_output=True,
            check=False,
        )
        self._untrack(unit)
