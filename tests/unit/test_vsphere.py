"""Unit tests for vSphere provider (VSphereUnit and VSphereUnitProvider)."""

import pytest

from kube_galaxy.pkg.manifest.models import NodeRole, NodesConfig
from kube_galaxy.pkg.units._base import RunResult, Unit
from kube_galaxy.pkg.units.vsphere import (
    VSphereUnit,
    VSphereUnitProvider,
    _govc_vm_ip,
    print_dependency_status,
)
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.shell import ShellError

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_run_result(returncode: int = 0, stdout: str = "", stderr: str = ""):  # type: ignore[misc]
    return type("R", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr})()


# ---------------------------------------------------------------------------
# print_dependency_status
# ---------------------------------------------------------------------------


def test_print_dependency_status_succeeds(monkeypatch):
    """`print_dependency_status` completes without error when govc/ssh/scp are available."""
    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.check_version", lambda _: None)
    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.check_installed", lambda _: None)
    print_dependency_status()  # must not raise


def test_print_dependency_status_raises_when_govc_missing(monkeypatch):
    """`print_dependency_status` raises ComponentError when govc is not found."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.check_version",
        lambda _: (_ for _ in ()).throw(ShellError(["govc", "--version"], 1, "not found")),
    )
    with pytest.raises(ComponentError, match="prerequisites not met"):
        print_dependency_status()


# ---------------------------------------------------------------------------
# _govc_vm_ip helper
# ---------------------------------------------------------------------------


def test_govc_vm_ip_returns_ip(monkeypatch):
    """`_govc_vm_ip` returns the stripped IP from govc vm.ip output."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(stdout="10.0.0.42\n"),
    )
    assert _govc_vm_ip("test-vm") == "10.0.0.42"


def test_govc_vm_ip_raises_on_failure(monkeypatch):
    """`_govc_vm_ip` raises ComponentError when govc vm.ip fails."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(returncode=1, stderr="not found"),
    )
    with pytest.raises(ComponentError, match="Failed to retrieve IP"):
        _govc_vm_ip("test-vm")


def test_govc_vm_ip_raises_on_empty_ip(monkeypatch):
    """`_govc_vm_ip` raises ComponentError when govc returns an empty IP."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(stdout=""),
    )
    with pytest.raises(ComponentError, match="empty IP"):
        _govc_vm_ip("test-vm")


# ---------------------------------------------------------------------------
# VSphereUnit — basic properties
# ---------------------------------------------------------------------------


def test_vsphere_unit_name():
    unit = VSphereUnit("test-vm", "10.0.0.1", NodeRole.CONTROL_PLANE, 0)
    assert unit.name == "test-vm"


def test_vsphere_unit_implements_unit_abc():
    """VSphereUnit has no unimplemented abstract methods — ABC compliant."""
    unit = VSphereUnit("abc", "10.0.0.1", NodeRole.CONTROL_PLANE, 0)
    assert isinstance(unit, Unit)


def test_vsphere_unit_role_and_index():
    unit = VSphereUnit("vm-1", "10.0.0.1", NodeRole.WORKER, 2)
    assert unit.role == NodeRole.WORKER
    assert unit.index == 2


# ---------------------------------------------------------------------------
# VSphereUnit._ssh_run
# ---------------------------------------------------------------------------


def test_vsphere_unit_ssh_run_builds_correct_command(monkeypatch):
    """`_ssh_run` prepends ssh -o StrictHostKeyChecking=no root@<ip> to the command."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):  # type: ignore[misc]
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.subprocess.run", fake_subproc)

    unit = VSphereUnit("test-vm", "10.0.0.42", NodeRole.CONTROL_PLANE, 0)
    unit._ssh_run(["echo", "hello"])

    assert recorded[0][0] == "ssh"
    assert "-o" in recorded[0]
    assert "StrictHostKeyChecking=no" in recorded[0]
    assert "root@10.0.0.42" in recorded[0]


def test_vsphere_unit_ssh_run_injects_env_vars(monkeypatch):
    """`_ssh_run` passes env vars as KEY=VALUE prefixes in the remote command."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):  # type: ignore[misc]
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.subprocess.run", fake_subproc)

    unit = VSphereUnit("test-vm", "10.0.0.42", NodeRole.CONTROL_PLANE, 0)
    unit._ssh_run(["env"], env={"FOO": "bar"})

    # The last arg is the remote command string containing the env prefix
    remote_cmd = recorded[0][-1]
    assert "FOO=bar" in remote_cmd
    assert "env" in remote_cmd


def test_vsphere_unit_ssh_run_raises_on_failure(monkeypatch):
    """`_ssh_run(check=True)` raises ShellError when the command exits non-zero."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(returncode=1, stderr="connection refused"),
    )

    unit = VSphereUnit("test-vm", "10.0.0.42", NodeRole.CONTROL_PLANE, 0)
    with pytest.raises(ShellError):
        unit._ssh_run(["false"], check=True)


def test_vsphere_unit_ssh_run_no_raise_when_check_false(monkeypatch):
    """`_ssh_run(check=False)` returns the result even on non-zero exit."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(returncode=1, stderr="err"),
    )

    unit = VSphereUnit("test-vm", "10.0.0.42", NodeRole.CONTROL_PLANE, 0)
    result = unit._ssh_run(["false"], check=False)
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# VSphereUnit.run — privileged flag is silently ignored
# ---------------------------------------------------------------------------


def test_vsphere_unit_run_privileged_ignored(monkeypatch):
    """`run(privileged=True)` behaves identically to `run(privileged=False)`."""
    calls: list[bool] = []

    def spy_ssh_run(self, cmd, **kwargs):  # type: ignore[misc]
        calls.append(True)
        return RunResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(VSphereUnit, "_ssh_run", spy_ssh_run)

    unit = VSphereUnit("test-vm", "10.0.0.42", NodeRole.CONTROL_PLANE, 0)
    unit.run(["hostname"], privileged=True)
    unit.run(["hostname"], privileged=False)

    assert len(calls) == 2


# ---------------------------------------------------------------------------
# VSphereUnit.put
# ---------------------------------------------------------------------------


def test_vsphere_unit_put_builds_correct_command(monkeypatch, tmp_path):
    """`put()` calls scp with -o StrictHostKeyChecking=no and root@<ip>:<remote>."""
    src = tmp_path / "file.txt"
    src.write_bytes(b"data")

    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):  # type: ignore[misc]
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.subprocess.run", fake_subproc)

    unit = VSphereUnit("test-vm", "10.0.0.42", NodeRole.CONTROL_PLANE, 0)
    unit.put(src, "/remote/path/file.txt")

    assert "scp" in recorded[0]
    assert "StrictHostKeyChecking=no" in recorded[0]
    assert str(src) in recorded[0]
    assert "root@10.0.0.42:/remote/path/file.txt" in recorded[0]


def test_vsphere_unit_put_raises_on_failure(monkeypatch, tmp_path):
    """`put()` raises ComponentError when scp fails."""
    src = tmp_path / "file.txt"
    src.write_bytes(b"data")

    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(returncode=1, stderr="permission denied"),
    )

    unit = VSphereUnit("test-vm", "10.0.0.42", NodeRole.CONTROL_PLANE, 0)
    with pytest.raises(ComponentError, match="Failed to scp"):
        unit.put(src, "/remote/path/file.txt")


# ---------------------------------------------------------------------------
# VSphereUnit.get
# ---------------------------------------------------------------------------


def test_vsphere_unit_get_builds_correct_command(monkeypatch, tmp_path):
    """`get()` calls scp with correct source and destination."""
    dest = tmp_path / "out" / "file.txt"
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):  # type: ignore[misc]
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.subprocess.run", fake_subproc)

    unit = VSphereUnit("test-vm", "10.0.0.42", NodeRole.CONTROL_PLANE, 0)
    unit.get("/remote/file.txt", dest)

    assert "scp" in recorded[0]
    assert "root@10.0.0.42:/remote/file.txt" in recorded[0]
    assert str(dest) in recorded[0]


def test_vsphere_unit_get_raises_on_failure(monkeypatch, tmp_path):
    """`get()` raises ComponentError when scp fails."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(returncode=1, stderr="no such file"),
    )

    unit = VSphereUnit("test-vm", "10.0.0.42", NodeRole.CONTROL_PLANE, 0)
    with pytest.raises(ComponentError, match="Failed to scp"):
        unit.get("/remote/missing.txt", tmp_path / "out.txt")


# ---------------------------------------------------------------------------
# VSphereUnitProvider — basic properties
# ---------------------------------------------------------------------------


def test_vsphere_provider_is_ephemeral():
    """`VSphereUnitProvider.is_ephemeral` must be True."""
    p = VSphereUnitProvider(
        NodesConfig(control_plane=1, worker=0),
        image="ubuntu-template",
        datacenter="DC1",
        datastore="ds1",
        network="VM Network",
    )
    assert p.is_ephemeral is True


# ---------------------------------------------------------------------------
# VSphereUnitProvider.provision
# ---------------------------------------------------------------------------


def test_vsphere_provider_provision_clones_and_powers_on(monkeypatch):
    """`provision()` runs govc vm.clone, govc vm.power -on, and retrieves IP."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):  # type: ignore[misc]
        recorded.append(list(cmd))
        # Return IP for the vm.ip call
        if "vm.ip" in cmd:
            return _make_run_result(stdout="10.0.0.42\n")
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.subprocess.run", fake_subproc)

    p = VSphereUnitProvider(
        NodesConfig(control_plane=1, worker=0),
        image="ubuntu-template",
        datacenter="DC1",
        datastore="ds1",
        network="VM Network",
    )
    unit = p.provision(NodeRole.CONTROL_PLANE, 0)

    assert isinstance(unit, VSphereUnit)
    assert unit.name == "kube-galaxy-control-plane-0"

    # Verify govc clone was called with datacenter, datastore, network flags
    clone_cmd = recorded[0]
    assert "vm.clone" in clone_cmd
    assert "-dc" in clone_cmd
    assert "DC1" in clone_cmd
    assert "-ds" in clone_cmd
    assert "ds1" in clone_cmd
    assert "-net" in clone_cmd
    assert "VM Network" in clone_cmd

    # Verify power-on
    power_cmd = recorded[1]
    assert "vm.power" in power_cmd
    assert "-on" in power_cmd

    # Verify vm.ip
    ip_cmd = recorded[2]
    assert "vm.ip" in ip_cmd


def test_vsphere_provider_provision_raises_on_clone_failure(monkeypatch):
    """`provision()` raises ComponentError when govc vm.clone fails."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(returncode=1, stderr="clone failed"),
    )

    p = VSphereUnitProvider(NodesConfig(), image="ubuntu-template")
    with pytest.raises(ComponentError, match="Failed to clone"):
        p.provision(NodeRole.CONTROL_PLANE, 0)


def test_vsphere_provider_provision_raises_on_power_failure(monkeypatch):
    """`provision()` raises ComponentError when govc vm.power fails."""
    call_count = {"n": 0}

    def fake_subproc(cmd, **kw):  # type: ignore[misc]
        call_count["n"] += 1
        if call_count["n"] == 1:  # clone succeeds
            return _make_run_result()
        # power-on fails
        return _make_run_result(returncode=1, stderr="power failed")

    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.subprocess.run", fake_subproc)

    p = VSphereUnitProvider(NodesConfig(), image="ubuntu-template")
    with pytest.raises(ComponentError, match="Failed to power on"):
        p.provision(NodeRole.CONTROL_PLANE, 0)


def test_vsphere_provider_provision_without_optional_flags(monkeypatch):
    """`provision()` omits -dc/-ds/-net flags when not configured."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):  # type: ignore[misc]
        recorded.append(list(cmd))
        if "vm.ip" in cmd:
            return _make_run_result(stdout="10.0.0.42\n")
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.subprocess.run", fake_subproc)

    p = VSphereUnitProvider(NodesConfig(), image="ubuntu-template")
    p.provision(NodeRole.CONTROL_PLANE, 0)

    clone_cmd = recorded[0]
    assert "-dc" not in clone_cmd
    assert "-ds" not in clone_cmd
    assert "-net" not in clone_cmd


# ---------------------------------------------------------------------------
# VSphereUnitProvider.locate
# ---------------------------------------------------------------------------


def test_vsphere_provider_locate_deterministic_name(monkeypatch):
    """`locate()` returns a VSphereUnit with the expected deterministic name."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(stdout="10.0.0.42\n"),
    )

    p = VSphereUnitProvider(NodesConfig(), image="ubuntu-template")
    u = p.locate(NodeRole.CONTROL_PLANE, 0)

    assert isinstance(u, VSphereUnit)
    assert u.name == "kube-galaxy-control-plane-0"


def test_vsphere_provider_locate_worker(monkeypatch):
    """`locate()` builds the correct name for worker nodes."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(stdout="10.0.0.43\n"),
    )

    p = VSphereUnitProvider(NodesConfig(control_plane=1, worker=2), image="ubuntu-template")
    u = p.locate(NodeRole.WORKER, 1)

    assert u.name == "kube-galaxy-worker-1"


def test_vsphere_provider_locate_dedup(monkeypatch):
    """`locate_all()` called twice does not duplicate units."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.vsphere.subprocess.run",
        lambda cmd, **kw: _make_run_result(stdout="10.0.0.42\n"),
    )

    p = VSphereUnitProvider(NodesConfig(), image="ubuntu-template")
    p.locate_all()
    p.locate_all()
    assert len(p._units) == 1


# ---------------------------------------------------------------------------
# VSphereUnitProvider.deprovision
# ---------------------------------------------------------------------------


def test_vsphere_provider_deprovision_calls_destroy(monkeypatch):
    """`deprovision()` runs govc vm.destroy and untracks the unit."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):  # type: ignore[misc]
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.subprocess.run", fake_subproc)

    p = VSphereUnitProvider(NodesConfig(), image="ubuntu-template")
    unit = VSphereUnit("kube-galaxy-control-plane-0", "10.0.0.42", NodeRole.CONTROL_PLANE, 0)
    p._track(unit)
    assert len(p._units) == 1

    p.deprovision(unit)

    assert any("vm.destroy" in cmd for cmd in recorded)
    assert any("kube-galaxy-control-plane-0" in cmd for cmd in recorded)
    assert len(p._units) == 0


def test_vsphere_provider_deprovision_all(monkeypatch):
    """`deprovision_all()` destroys all tracked units."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):  # type: ignore[misc]
        recorded.append(list(cmd))
        if "vm.ip" in cmd:
            return _make_run_result(stdout="10.0.0.42\n")
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.subprocess.run", fake_subproc)

    p = VSphereUnitProvider(
        NodesConfig(control_plane=1, worker=1),
        image="ubuntu-template",
    )
    p.locate_all()
    assert len(p._units) == 2

    p.deprovision_all()

    destroy_cmds = [cmd for cmd in recorded if "vm.destroy" in cmd]
    assert len(destroy_cmds) == 2
    assert len(p._units) == 0
