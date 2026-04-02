"""Unit tests for the units package: Unit ABC, LocalUnit."""

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from kube_galaxy.pkg.manifest.models import NodeRole, NodesConfig
from kube_galaxy.pkg.units._base import RunResult, Unit
from kube_galaxy.pkg.units.juju import (
    JujuUnit,
    JujuUnitProvider,
    _get_application_status,
    _get_state,
    _get_unit_status,
    _get_workload_status,
    print_dependency_status,
)
from kube_galaxy.pkg.units.local import LocalUnit, LocalUnitProvider
from kube_galaxy.pkg.units.lxdvm import LXDUnit
from kube_galaxy.pkg.units.ssh import SSHUnit, SSHUnitProvider
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError
from kube_galaxy.pkg.utils.shell import ShellError

# ---------------------------------------------------------------------------
# RunResult dataclass
# ---------------------------------------------------------------------------


def test_run_result_fields():
    r = RunResult(returncode=0, stdout="hello", stderr="")
    assert r.returncode == 0
    assert r.stdout == "hello"
    assert r.stderr == ""


# ---------------------------------------------------------------------------
# Unit ABC — cannot be instantiated directly
# ---------------------------------------------------------------------------


def test_unit_is_abstract():
    with pytest.raises(TypeError):
        Unit()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# LocalUnit — basic properties
# ---------------------------------------------------------------------------


def test_local_unit_name():
    u = LocalUnit()
    assert u.name == "local"


def test_local_unit_arch_is_cached():
    u = LocalUnit()
    arch1 = u.arch
    arch2 = u.arch
    assert arch1 is arch2  # cached_property returns same object


# ---------------------------------------------------------------------------
# LocalUnit.run — privilege escalation
# ---------------------------------------------------------------------------


def test_local_unit_run_no_sudo_when_not_privileged(monkeypatch):
    """run() without privileged=True never prepends sudo."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("kube_galaxy.pkg.units.local.subprocess.run", fake_subproc)
    monkeypatch.setattr("kube_galaxy.pkg.units.local.os.getuid", lambda: 1000)

    u = LocalUnit()
    u.run(["echo", "hello"], privileged=False)

    assert len(recorded) == 1
    assert recorded[0][0] != "sudo"
    assert "echo" in recorded[0]


def test_local_unit_run_sudo_when_privileged_and_not_root(monkeypatch):
    """run(privileged=True) prepends sudo when os.getuid() != 0."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("kube_galaxy.pkg.units.local.subprocess.run", fake_subproc)
    monkeypatch.setattr("kube_galaxy.pkg.units.local.os.getuid", lambda: 1000)

    u = LocalUnit()
    u.run(["systemctl", "start", "foo"], privileged=True)

    assert len(recorded) == 1
    assert recorded[0][0] == "sudo"
    assert "systemctl" in recorded[0]


def test_local_unit_run_no_sudo_when_root(monkeypatch):
    """run(privileged=True) does NOT prepend sudo when os.getuid() == 0."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("kube_galaxy.pkg.units.local.subprocess.run", fake_subproc)
    monkeypatch.setattr("kube_galaxy.pkg.units.local.os.getuid", lambda: 0)

    u = LocalUnit()
    u.run(["systemctl", "start", "foo"], privileged=True)

    assert len(recorded) == 1
    assert recorded[0][0] == "systemctl"
    assert "sudo" not in recorded[0]


# ---------------------------------------------------------------------------
# LocalUnit.download — delegates to download_file
# ---------------------------------------------------------------------------


def test_local_unit_download_delegates(monkeypatch, tmp_path):
    """LocalUnit.download() calls download_file with the correct arguments."""
    calls: list[tuple[str, Path]] = []

    def fake_download_file(url: str, dest: Path) -> None:
        calls.append((url, dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"data")

    # download_file is imported lazily inside the method; patch in the utils module
    monkeypatch.setattr("kube_galaxy.pkg.utils.components.download_file", fake_download_file)

    u = LocalUnit()
    dest = str(tmp_path / "file.tar.gz")
    u.download("https://example.com/file.tar.gz", dest)

    assert len(calls) == 1
    url, path = calls[0]
    assert url == "https://example.com/file.tar.gz"
    assert path == Path(dest)


# ---------------------------------------------------------------------------
# LocalUnit.extract — delegates to extract_archive
# ---------------------------------------------------------------------------


def test_local_unit_extract_delegates(monkeypatch, tmp_path):
    """LocalUnit.extract() calls extract_archive with the correct arguments."""
    calls: list[tuple[Path, Path]] = []

    def fake_extract_archive(archive: Path, dest: Path) -> None:
        calls.append((archive, dest))

    # extract_archive is imported lazily inside the method; patch in the utils module
    monkeypatch.setattr("kube_galaxy.pkg.utils.components.extract_archive", fake_extract_archive)

    u = LocalUnit()
    archive = str(tmp_path / "foo.tar.gz")
    dest = str(tmp_path / "out")
    u.extract(archive, dest)

    assert len(calls) == 1
    assert calls[0] == (Path(archive), Path(dest))


# ---------------------------------------------------------------------------
# LocalUnit.extract_zip
# ---------------------------------------------------------------------------


def test_local_unit_extract_zip(tmp_path):
    """LocalUnit.extract_zip() extracts a single file from a zip archive."""
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("inner/binary", b"binary-content")

    out_path = tmp_path / "out" / "binary"
    u = LocalUnit()
    u.extract_zip(str(zip_path), "inner/binary", str(out_path))

    assert out_path.exists()
    assert out_path.read_bytes() == b"binary-content"


def test_local_unit_extract_zip_missing_entry_raises(tmp_path):
    """LocalUnit.extract_zip() raises ComponentError for missing zip entry."""
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("other/file", b"data")

    u = LocalUnit()
    with pytest.raises(ComponentError, match="Failed to extract"):
        u.extract_zip(str(zip_path), "nonexistent/path", str(tmp_path / "out"))


# ---------------------------------------------------------------------------
# LXDUnit — importability and ABC compliance
# ---------------------------------------------------------------------------


def test_lxd_unit_importable():
    """LXDUnit can be imported and instantiated without error."""
    unit = LXDUnit("test-container", NodeRole.CONTROL_PLANE, 0)
    assert unit.name == "test-container"


def test_lxd_unit_implements_unit_abc():
    """LXDUnit has no unimplemented abstract methods — mypy/ABC compliant."""
    # If LXDUnit is missing any abstract method, this will raise TypeError
    unit = LXDUnit("abc", NodeRole.CONTROL_PLANE, 0)
    assert isinstance(unit, Unit)


# ---------------------------------------------------------------------------
# LocalUnit.enlist — no-op
# ---------------------------------------------------------------------------


def test_local_unit_enlist_is_noop():
    """LocalUnit.enlist() returns immediately without error."""
    u = LocalUnit()
    u.enlist("127.0.0.1")  # must not raise
    u.enlist("127.0.0.1", timeout=60)  # also no-op with explicit timeout


# ---------------------------------------------------------------------------
# LXDUnit.enlist — retry / timeout behaviour
# ---------------------------------------------------------------------------


def test_lxd_unit_enlist_returns_immediately_when_agent_up(monkeypatch):
    """enlist() returns immediately if hostname succeeds on first try."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return type("R", (), {"returncode": 0, "stdout": "my-host\n", "stderr": ""})()

    monkeypatch.setattr("kube_galaxy.pkg.units.lxdvm.subprocess.run", fake_run)

    unit = LXDUnit("test-vm", NodeRole.CONTROL_PLANE, 0)
    unit.enlist("10.0.0.1", timeout=30)

    # Only one lxc exec call was needed
    assert len(calls) == 3
    assert "hostname" in calls[0]


def test_lxd_unit_enlist_zero_timeout_succeeds_if_ready(monkeypatch):
    """enlist(timeout=0) returns immediately when agent responds."""

    def fake_run(cmd, **kwargs):
        return type("R", (), {"returncode": 0, "stdout": "my-host\n", "stderr": ""})()

    monkeypatch.setattr("kube_galaxy.pkg.units.lxdvm.subprocess.run", fake_run)

    unit = LXDUnit("test-vm", NodeRole.CONTROL_PLANE, 0)
    unit.enlist("10.0.0.1", timeout=0)  # must not raise


def test_lxd_unit_enlist_retries_on_failure(monkeypatch):
    """enlist() retries when lxc exec returns non-zero."""
    attempt = {"count": 0}

    def fake_run(cmd, **kwargs):
        if "hostname" in cmd:
            attempt["count"] += 1
            # Fail the first two times, succeed on the third
            rc = 0 if attempt["count"] >= 3 else 255
            stderr = "VM agent isn't running"
            return type("R", (), {"returncode": rc, "stdout": "", "stderr": stderr})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("kube_galaxy.pkg.units.lxdvm.subprocess.run", fake_run)
    monkeypatch.setattr("kube_galaxy.pkg.units._base.time.sleep", lambda _: None)

    unit = LXDUnit("test-vm", NodeRole.CONTROL_PLANE, 0)
    unit.enlist("10.0.0.1", timeout=60)

    assert attempt["count"] == 3


def test_lxd_unit_enlist_raises_on_timeout(monkeypatch):
    """enlist() raises ClusterError when the timeout elapses."""

    def fake_run(cmd, **kwargs):
        stderr = "VM agent isn't running"
        return type("R", (), {"returncode": 255, "stdout": "", "stderr": stderr})()

    # Simulate time passing: first call returns t=0, subsequent return t=deadline+1
    times = iter([0.0, 0.0, 200.0])

    monkeypatch.setattr("kube_galaxy.pkg.units.lxdvm.subprocess.run", fake_run)
    monkeypatch.setattr("kube_galaxy.pkg.units._base.time.monotonic", lambda: next(times))
    monkeypatch.setattr("kube_galaxy.pkg.units._base.time.sleep", lambda _: None)

    unit = LXDUnit("test-vm", NodeRole.CONTROL_PLANE, 0)
    with pytest.raises(ClusterError, match="Timed out waiting for unit 'test-vm'"):
        unit.enlist("10.0.0.1", timeout=120)


# ---------------------------------------------------------------------------
# UnitProvider.locate_all / provision_all — base class auto-tracking
# ---------------------------------------------------------------------------


def test_local_provider_locate_all_populates_units():
    """locate_all() on LocalUnitProvider must produce a non-empty unit list."""
    p = LocalUnitProvider(NodesConfig(control_plane=1, worker=0), image="")
    units = p.locate_all()
    assert len(units) == 1
    assert isinstance(units[0], LocalUnit)


def test_local_provider_provision_all_populates_units():
    """provision_all() on LocalUnitProvider must produce a non-empty unit list."""
    p = LocalUnitProvider(NodesConfig(control_plane=1, worker=0), image="")
    units = p.provision_all()
    assert len(units) == 1
    assert isinstance(units[0], LocalUnit)


def test_local_provider_provision_all_no_duplicate_tracking():
    """provision_all() must not add duplicate units even if called twice."""
    p = LocalUnitProvider(NodesConfig(control_plane=1, worker=0), image="")
    p.provision_all()
    p.provision_all()
    assert len(p._units) == 1


def test_ssh_provider_locate_all_populates_units():
    """locate_all() on SSHUnitProvider must populate _units for each host."""
    counts = NodesConfig(control_plane=1, worker=1)
    p = SSHUnitProvider(counts, image="", hosts=["host-cp", "host-w0"])
    units = p.locate_all()
    assert len(units) == 2
    assert all(isinstance(u, SSHUnit) for u in units)


def test_ssh_provider_provision_all_populates_units():
    """provision_all() on SSHUnitProvider must populate _units for each host."""
    counts = NodesConfig(control_plane=1, worker=1)
    p = SSHUnitProvider(counts, image="", hosts=["host-cp", "host-w0"])
    units = p.provision_all()
    assert len(units) == 2
    assert all(isinstance(u, SSHUnit) for u in units)


def test_ssh_provider_provision_all_no_extra_locate_calls():
    """provision_all() must call provision once per slot (no extra locate call)."""
    counts = NodesConfig(control_plane=1, worker=0)
    p = SSHUnitProvider(counts, image="", hosts=["host-cp"])
    provision_calls: list[tuple[NodeRole, int]] = []
    locate_calls: list[tuple[NodeRole, int]] = []
    original_provision = p.provision
    original_locate = p.locate

    def spy_provision(role: NodeRole, index: int) -> SSHUnit:
        provision_calls.append((role, index))
        return original_provision(role, index)

    def spy_locate(role: NodeRole, index: int) -> SSHUnit:
        locate_calls.append((role, index))
        return original_locate(role, index)

    p.provision = spy_provision  # type: ignore[method-assign]
    p.locate = spy_locate  # type: ignore[method-assign]

    p.provision_all()

    assert len(provision_calls) == 1
    assert len(locate_calls) == 0


# ---------------------------------------------------------------------------
# _get_state — module-level helper
# ---------------------------------------------------------------------------

_FULL_STATE = {
    "applications": {
        "myapp": {
            "units": {
                "myapp/0": {
                    "workload-status": {"current": "active"},
                    "juju-status": {"current": "idle"},
                },
            }
        }
    }
}


def _make_run_result(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return type("R", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr})()


def test_get_state_returns_parsed_json(monkeypatch):
    """_get_state() returns parsed dict when juju status exits 0 with valid JSON."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    result = _get_state()
    assert result == _FULL_STATE


def test_get_state_returns_empty_on_nonzero(monkeypatch):
    """_get_state() returns {} when juju status exits non-zero."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(returncode=1, stdout="", stderr="error"),
    )
    assert _get_state() == {}


def test_get_state_returns_empty_on_invalid_json(monkeypatch):
    """_get_state() returns {} when output is not valid JSON."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout="not json at all"),
    )
    assert _get_state() == {}


def test_get_state_returns_empty_when_json_is_not_dict(monkeypatch):
    """_get_state() returns {} when JSON output is a list, not a dict."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout="[1, 2, 3]"),
    )
    assert _get_state() == {}


# ---------------------------------------------------------------------------
# _get_application_status
# ---------------------------------------------------------------------------


def test_get_application_status_returns_app_dict(monkeypatch):
    """`_get_application_status` extracts the application sub-dict."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    result = _get_application_status("myapp")
    assert "units" in result


def test_get_application_status_returns_empty_for_missing_app(monkeypatch):
    """`_get_application_status` returns {} when app is absent from state."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    assert _get_application_status("nonexistent") == {}


# ---------------------------------------------------------------------------
# _get_unit_status
# ---------------------------------------------------------------------------


def test_get_unit_status_returns_unit_dict(monkeypatch):
    """`_get_unit_status` extracts the unit sub-dict."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    result = _get_unit_status("myapp/0")
    assert "workload-status" in result


def test_get_unit_status_returns_empty_for_missing_unit(monkeypatch):
    """`_get_unit_status` returns {} when unit is absent."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    assert _get_unit_status("myapp/99") == {}


# ---------------------------------------------------------------------------
# _get_workload_status
# ---------------------------------------------------------------------------


def test_get_workload_status_returns_tuple(monkeypatch):
    """`_get_workload_status` returns (workload, juju) strings."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    result = _get_workload_status("myapp/0")
    assert result == ("active", "idle")


def test_get_workload_status_returns_none_for_missing_unit(monkeypatch):
    """`_get_workload_status` returns None when unit is not found."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    assert _get_workload_status("myapp/99") is None


# ---------------------------------------------------------------------------
# print_dependency_status
# ---------------------------------------------------------------------------


def test_print_dependency_status_succeeds(monkeypatch):
    """`print_dependency_status` completes without error when juju is available."""
    monkeypatch.setattr("kube_galaxy.pkg.units.juju.check_version", lambda _: None)
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    print_dependency_status()  # must not raise


def test_print_dependency_status_raises_when_juju_missing(monkeypatch):
    """`print_dependency_status` raises ComponentError when juju is not found."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.check_version",
        lambda _: (_ for _ in ()).throw(ShellError(["juju", "--version"], 1, "not found")),
    )
    with pytest.raises(ComponentError, match="'juju' not found"):
        print_dependency_status()


def test_print_dependency_status_raises_when_status_invalid(monkeypatch):
    """`print_dependency_status` raises ComponentError when juju status returns no JSON."""
    monkeypatch.setattr("kube_galaxy.pkg.units.juju.check_version", lambda _: None)
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(returncode=1),
    )
    with pytest.raises(ComponentError, match="did not return valid JSON"):
        print_dependency_status()


# ---------------------------------------------------------------------------
# JujuUnit — basic properties
# ---------------------------------------------------------------------------


def test_juju_unit_name():
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    assert unit.name == "myapp/0"


def test_juju_unit_application():
    assert JujuUnit.application("myapp/0") == "myapp"
    assert JujuUnit.application("other-app/3") == "other-app"


# ---------------------------------------------------------------------------
# JujuUnit._juju_exec
# ---------------------------------------------------------------------------


def test_juju_unit_exec_builds_correct_command(monkeypatch):
    """`_juju_exec` prepends juju exec --unit <name> -- to the command."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.run", fake_subproc)

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    unit._juju_exec(["echo", "hello"])

    assert recorded[0][:4] == ["juju", "exec", "--unit", "myapp/0"]
    assert "echo" in recorded[0]
    assert "hello" in recorded[0]


def test_juju_unit_exec_injects_env_vars(monkeypatch):
    """`_juju_exec` passes KEY=VALUE pairs as positional args after '--' when env is provided."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.run", fake_subproc)

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    unit._juju_exec(["env"], env={"FOO": "bar", "BAZ": "qux"})

    cmd = recorded[0]
    assert "--env" not in cmd
    assert "FOO=bar" in cmd
    assert "BAZ=qux" in cmd
    # env vars must appear after '--' and before the command itself
    sep = cmd.index("--")
    env_section = cmd[sep + 1 :]
    assert "FOO=bar" in env_section
    assert "BAZ=qux" in env_section
    assert cmd[-1] == "env"


def test_juju_unit_exec_raises_shell_error_on_failure(monkeypatch):
    """`_juju_exec(check=True)` raises ShellError when the command exits non-zero."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.subprocess.run",
        lambda cmd, **kw: _make_run_result(returncode=1, stderr="boom"),
    )

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    with pytest.raises(ShellError):
        unit._juju_exec(["false"], check=True)


def test_juju_unit_exec_no_raise_when_check_false(monkeypatch):
    """`_juju_exec(check=False)` returns the result even on non-zero exit."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.subprocess.run",
        lambda cmd, **kw: _make_run_result(returncode=1, stderr="err"),
    )

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    result = unit._juju_exec(["false"], check=False)
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# JujuUnit.run — privileged flag is silently ignored
# ---------------------------------------------------------------------------


def test_juju_unit_run_privileged_ignored(monkeypatch):
    """`run(privileged=True)` behaves identically to `run(privileged=False)`."""
    calls: list[bool] = []

    def spy_exec(self, cmd, **kwargs):
        calls.append(True)
        return RunResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(JujuUnit, "_juju_exec", spy_exec)

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    unit.run(["hostname"], privileged=True)
    unit.run(["hostname"], privileged=False)

    assert len(calls) == 2


# ---------------------------------------------------------------------------
# JujuUnit.put
# ---------------------------------------------------------------------------


def test_juju_unit_put_builds_correct_command(monkeypatch, tmp_path):
    """`put()` pre-creates the remote directory then calls juju scp with name:remote format."""
    src = tmp_path / "file.txt"
    src.write_bytes(b"data")

    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.run", fake_subproc)

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    unit.put(src, "/remote/path/file.txt")

    # First call: juju exec mkdir -p
    assert "mkdir" in recorded[0]
    # Second call: juju scp
    scp_cmd = recorded[1]
    assert "juju" in scp_cmd
    assert "scp" in scp_cmd
    assert str(src) in scp_cmd
    assert "root@myapp/0:/remote/path/file.txt" in scp_cmd


def test_juju_unit_put_raises_component_error_on_failure(monkeypatch, tmp_path):
    """`put()` raises ComponentError when juju scp fails (mkdir succeeds)."""
    src = tmp_path / "file.txt"
    src.write_bytes(b"data")

    call_count = {"n": 0}

    def fake_subproc(cmd, **kw):
        call_count["n"] += 1
        # First call is juju exec mkdir — let it succeed
        if call_count["n"] == 1:
            return _make_run_result()
        # Second call is juju scp — make it fail
        return _make_run_result(returncode=1, stderr="connection refused")

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.run", fake_subproc)

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    with pytest.raises(ComponentError, match="Failed to push"):
        unit.put(src, "/remote/path/file.txt")


# ---------------------------------------------------------------------------
# JujuUnit.get
# ---------------------------------------------------------------------------


def test_juju_unit_get_builds_correct_command(monkeypatch, tmp_path):
    """`get()` calls juju scp with correct source and destination."""
    dest = tmp_path / "out" / "file.txt"
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.run", fake_subproc)

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    unit.get("/remote/file.txt", dest)

    assert "juju" in recorded[0]
    assert "scp" in recorded[0]
    assert "root@myapp/0:/remote/file.txt" in recorded[0]
    assert str(dest) in recorded[0]


def test_juju_unit_get_raises_component_error_on_failure(monkeypatch, tmp_path):
    """`get()` raises ComponentError when juju scp fails."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.subprocess.run",
        lambda cmd, **kw: _make_run_result(returncode=1, stderr="no such file"),
    )

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    with pytest.raises(ComponentError, match="Failed to pull"):
        unit.get("/remote/missing.txt", tmp_path / "out.txt")


# ---------------------------------------------------------------------------
# JujuUnit.enlist
# ---------------------------------------------------------------------------


def test_juju_unit_enlist_returns_immediately_when_active_idle(monkeypatch):
    """`enlist()` returns immediately when unit is already active/idle."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.subprocess.run",
        lambda cmd, **kw: _make_run_result(),
    )
    monkeypatch.setattr("kube_galaxy.pkg.units._base.Unit.update_etc_hosts", lambda self, ip: None)

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    unit.enlist("127.0.0.1", timeout=30)  # must not raise


def test_juju_unit_enlist_retries_until_active_idle(monkeypatch):
    """`enlist()` retries until the unit reports active/idle."""
    state_with_maintenance = {
        "applications": {
            "myapp": {
                "units": {
                    "myapp/0": {
                        "workload-status": {"current": "maintenance"},
                        "juju-status": {"current": "executing"},
                    }
                }
            }
        }
    }
    attempt = {"count": 0}

    def fake_run(cmd, **kw):
        attempt["count"] += 1
        if attempt["count"] >= 3:
            return _make_run_result(stdout=json.dumps(_FULL_STATE))
        return _make_run_result(stdout=json.dumps(state_with_maintenance))

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.run", fake_run)
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.subprocess.run",
        lambda cmd, **kw: _make_run_result(),
    )
    monkeypatch.setattr("kube_galaxy.pkg.units._base.Unit.update_etc_hosts", lambda self, ip: None)
    monkeypatch.setattr("kube_galaxy.pkg.units.juju.time.sleep", lambda _: None)

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    unit.enlist("127.0.0.1", timeout=60)

    assert attempt["count"] >= 3


def test_juju_unit_enlist_raises_on_timeout(monkeypatch):
    """`enlist()` raises ClusterError when timeout elapses without becoming active/idle."""
    times = iter([0.0, 0.0, 9999.0])

    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(returncode=1),
    )
    monkeypatch.setattr("kube_galaxy.pkg.units.juju.time.monotonic", lambda: next(times))
    monkeypatch.setattr("kube_galaxy.pkg.units.juju.time.sleep", lambda _: None)

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    with pytest.raises(ClusterError, match="Timed out waiting for unit 'myapp/0'"):
        unit.enlist("127.0.0.1", timeout=120)


# ---------------------------------------------------------------------------
# JujuUnitProvider
# ---------------------------------------------------------------------------


def test_juju_provider_is_ephemeral():
    """`JujuUnitProvider.is_ephemeral` must be True."""
    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=0), image="ubuntu:22.04")
    assert p.is_ephemeral is True


def test_juju_provider_provision_index0_deploys(monkeypatch):
    """`provision(index=0)` runs `juju deploy`."""
    recorded: list[list[str]] = []

    _models_response = json.dumps(
        {"current-model": "default", "models": [{"short-name": "default", "type": "lxd"}]}
    )

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        # Return model JSON for the _cloud_type() call, success for everything else
        if "models" in cmd:
            return _make_run_result(stdout=_models_response)
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.run", fake_subproc)
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju._get_application_status",
        lambda app, **kw: {
            "units": {"kube-galaxy-control-plane/0": {"workload-status": {"current": "active"}}}
        },
    )

    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=0), image="ubuntu:22.04")
    unit = p.provision(NodeRole.CONTROL_PLANE, 0)

    assert any("deploy" in cmd for cmd in recorded)
    assert isinstance(unit, JujuUnit)


def test_juju_provider_provision_index1_adds_unit(monkeypatch):
    """`provision(index>0)` runs `juju add-unit` instead of deploy."""
    recorded: list[list[str]] = []

    _models_response = json.dumps(
        {"current-model": "default", "models": [{"short-name": "default", "type": "lxd"}]}
    )

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        if "models" in cmd:
            return _make_run_result(stdout=_models_response)
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.run", fake_subproc)
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju._get_application_status",
        lambda app, **kw: {
            "units": {
                "kube-galaxy-worker/0": {"workload-status": {"current": "active"}},
                "kube-galaxy-worker/1": {"workload-status": {"current": "active"}},
            }
        },
    )

    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=2), image="ubuntu:22.04")
    unit = p.provision(NodeRole.WORKER, 1)

    assert any("add-unit" in cmd for cmd in recorded)
    assert isinstance(unit, JujuUnit)


def test_juju_provider_provision_raises_on_failure(monkeypatch):
    """`provision()` raises ComponentError when juju deploy/add-unit fails."""
    _models_response = json.dumps(
        {"current-model": "default", "models": [{"short-name": "default", "type": "lxd"}]}
    )

    def fake_subproc(cmd, **kw):
        if "models" in cmd:
            return _make_run_result(stdout=_models_response)
        return _make_run_result(returncode=1, stderr="deploy failed")

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.run", fake_subproc)

    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=0), image="ubuntu:22.04")
    with pytest.raises(ComponentError, match="Failed to launch Juju machine"):
        p.provision(NodeRole.CONTROL_PLANE, 0)


def test_juju_provider_locate_returns_unit_by_sorted_index(monkeypatch):
    """`locate()` returns the JujuUnit at the sorted position matching `index`."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju._get_application_status",
        lambda app, **kw: {
            "units": {
                "kube-galaxy-worker/2": {},
                "kube-galaxy-worker/0": {},
                "kube-galaxy-worker/1": {},
            }
        },
    )

    p = JujuUnitProvider(NodesConfig(control_plane=0, worker=3), image="ubuntu:22.04")
    unit = p.locate(NodeRole.WORKER, 1)

    assert isinstance(unit, JujuUnit)
    assert unit.name == "kube-galaxy-worker/1"


def test_juju_provider_deprovision_index0_removes_application(monkeypatch):
    """`deprovision(unit)` for index 0 runs `juju remove-application`."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.run", fake_subproc)

    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=0), image="ubuntu:22.04")
    unit = JujuUnit("kube-galaxy-control-plane/0", NodeRole.CONTROL_PLANE, 0)
    p._track(unit)
    p.deprovision(unit)

    assert any("remove-application" in cmd for cmd in recorded)


def test_juju_provider_deprovision_index1_removes_unit(monkeypatch):
    """`deprovision(unit)` for index > 0 runs `juju remove-unit`."""
    recorded: list[list[str]] = []

    def fake_subproc(cmd, **kwargs):
        recorded.append(list(cmd))
        return _make_run_result()

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.run", fake_subproc)

    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=2), image="ubuntu:22.04")
    unit = JujuUnit("kube-galaxy-worker/1", NodeRole.WORKER, 1)
    p._track(unit)
    p.deprovision(unit)

    assert any("remove-unit" in cmd for cmd in recorded)


def test_juju_provider_deprovision_untracks_unit(monkeypatch):
    """`deprovision()` removes the unit from the tracked set."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.subprocess.run",
        lambda cmd, **kw: _make_run_result(),
    )

    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=0), image="ubuntu:22.04")
    unit = JujuUnit("kube-galaxy-control-plane/0", NodeRole.CONTROL_PLANE, 0)
    p._track(unit)
    assert len(p._units) == 1

    p.deprovision(unit)
    assert len(p._units) == 0


# ---------------------------------------------------------------------------
# JujuUnit — tunnel helpers
# ---------------------------------------------------------------------------


def test_juju_unit_tunnel_alive_false_when_no_tunnel():
    """`tunnel_alive()` returns False when no tunnel has been opened."""
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[8765])
    assert unit.tunnel_alive() is False


def test_juju_unit_open_tunnel_noop_when_no_ports():
    """`open_tunnel()` is a no-op when tunnel_ports is empty."""
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[])
    unit.open_tunnel()  # must not raise
    assert unit._tunnel is None


def test_juju_unit_open_tunnel_spawns_process(monkeypatch):
    """`open_tunnel()` spawns a subprocess with juju ssh -R flags."""
    spawned: list[list[str]] = []

    class FakePopen:
        def __init__(self, cmd: list[str]) -> None:
            spawned.append(cmd)

        def poll(self) -> None:
            return None

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.Popen", FakePopen)
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[8765, 5000])
    unit.open_tunnel()

    assert len(spawned) == 1
    cmd = spawned[0]
    assert cmd[:3] == ["juju", "ssh", "--no-host-key-checks"]
    assert "myapp/0" in cmd
    assert "-N" in cmd
    assert "-R" in cmd
    assert "8765:localhost:8765" in cmd
    assert "5000:localhost:5000" in cmd


def test_juju_unit_open_tunnel_idempotent(monkeypatch):
    """`open_tunnel()` is a no-op if the tunnel is already alive."""
    spawned: list[list[str]] = []

    class FakePopen:
        def __init__(self, cmd: list[str]) -> None:
            spawned.append(cmd)

        def poll(self) -> None:
            return None

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.Popen", FakePopen)
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[8765])
    unit.open_tunnel()
    unit.open_tunnel()  # second call should be a no-op

    assert len(spawned) == 1


def test_juju_unit_tunnel_alive_true_when_running(monkeypatch):
    """`tunnel_alive()` returns True while the tunnel process is running."""

    class FakePopen:
        def __init__(self, cmd: list[str]) -> None:
            pass

        def poll(self) -> None:
            return None  # still running

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.Popen", FakePopen)
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[8765])
    unit.open_tunnel()
    assert unit.tunnel_alive() is True


def test_juju_unit_stop_tunnel_terminates_process(monkeypatch):
    """`stop_tunnel()` terminates the tunnel process and sets _tunnel to None."""
    terminated: list[bool] = []

    class FakePopen:
        def __init__(self, cmd: list[str]) -> None:
            pass

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            terminated.append(True)

        def wait(self, timeout: float | None = None) -> int:
            return 0

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.Popen", FakePopen)
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[8765])
    unit.open_tunnel()
    unit.stop_tunnel()

    assert terminated == [True]
    assert unit._tunnel is None
    assert unit.tunnel_alive() is False


def test_juju_unit_stop_tunnel_noop_when_no_tunnel():
    """`stop_tunnel()` is a no-op when the tunnel is not running."""
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[8765])
    unit.stop_tunnel()  # must not raise
    assert unit._tunnel is None


def test_juju_unit_stop_tunnel_kills_on_timeout(monkeypatch):
    """`stop_tunnel()` kills the process if wait() times out."""
    killed: list[bool] = []

    class FakePopen:
        def __init__(self, cmd: list[str]) -> None:
            pass

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired(cmd="juju", timeout=5)

        def kill(self) -> None:
            killed.append(True)

    monkeypatch.setattr("kube_galaxy.pkg.units.juju.subprocess.Popen", FakePopen)
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[8765])
    unit.open_tunnel()
    unit.stop_tunnel()

    assert killed == [True]
    assert unit._tunnel is None


# ---------------------------------------------------------------------------
# JujuUnitProvider — orchestrator_ip, open_tunnels, stop_tunnels
# ---------------------------------------------------------------------------


def test_juju_provider_orchestrator_ip_returns_loopback():
    """`JujuUnitProvider.orchestrator_ip()` always returns '127.0.0.1'."""
    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=0), image="ubuntu:22.04")
    assert p.orchestrator_ip() == "127.0.0.1"


def test_juju_provider_open_tunnels_calls_open_on_juju_units(monkeypatch):
    """`open_tunnels()` calls `open_tunnel()` on each tracked JujuUnit."""
    opened: list[str] = []

    monkeypatch.setattr(JujuUnit, "open_tunnel", lambda self: opened.append(self.name))

    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=1), image="ubuntu:22.04")
    for name, role, idx in [
        ("kube-galaxy-control-plane/0", NodeRole.CONTROL_PLANE, 0),
        ("kube-galaxy-worker/0", NodeRole.WORKER, 0),
    ]:
        unit = JujuUnit(name, role, idx, tunnel_ports=[8765])
        p._track(unit)

    p.open_tunnels()

    assert sorted(opened) == sorted(
        [
            "kube-galaxy-control-plane/0",
            "kube-galaxy-worker/0",
        ]
    )


def test_juju_provider_stop_tunnels_calls_stop_on_juju_units(monkeypatch):
    """`stop_tunnels()` calls `stop_tunnel()` on each tracked JujuUnit."""
    stopped: list[str] = []

    monkeypatch.setattr(JujuUnit, "stop_tunnel", lambda self: stopped.append(self.name))

    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=0), image="ubuntu:22.04")
    unit = JujuUnit("kube-galaxy-control-plane/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[8765])
    p._track(unit)

    p.stop_tunnels()

    assert stopped == ["kube-galaxy-control-plane/0"]


def test_juju_provider_deprovision_stops_tunnel(monkeypatch):
    """`deprovision()` calls `stop_tunnel()` on the unit before removing it."""
    stopped: list[str] = []

    monkeypatch.setattr(JujuUnit, "stop_tunnel", lambda self: stopped.append(self.name))
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.subprocess.run",
        lambda cmd, **kw: _make_run_result(),
    )

    p = JujuUnitProvider(NodesConfig(control_plane=1, worker=0), image="ubuntu:22.04")
    unit = JujuUnit("kube-galaxy-control-plane/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[8765])
    p._track(unit)
    p.deprovision(unit)

    assert stopped == ["kube-galaxy-control-plane/0"]


def test_juju_unit_enlist_opens_tunnel_before_etc_hosts(monkeypatch):
    """`enlist()` opens the tunnel before writing /etc/hosts."""
    call_order: list[str] = []

    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.subprocess.run",
        lambda cmd, **kw: _make_run_result(),
    )
    monkeypatch.setattr(JujuUnit, "open_tunnel", lambda self: call_order.append("open_tunnel"))
    monkeypatch.setattr(
        "kube_galaxy.pkg.units._base.Unit.update_etc_hosts",
        lambda self, ip: call_order.append("update_etc_hosts"),
    )

    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0, tunnel_ports=[8765])
    unit.enlist("127.0.0.1", timeout=30)

    assert call_order == ["open_tunnel", "update_etc_hosts"]


# ---------------------------------------------------------------------------
# JujuUnit — public_address
# ---------------------------------------------------------------------------

_STATE_WITH_PUBLIC_IP = {
    "applications": {
        "myapp": {
            "units": {
                "myapp/0": {
                    "workload-status": {"current": "active"},
                    "juju-status": {"current": "idle"},
                    "public-address": "203.0.113.42",
                },
            }
        }
    }
}


def test_juju_unit_public_address_returns_field_from_status(monkeypatch):
    """public_address returns `public-address` field when present in Juju status."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_STATE_WITH_PUBLIC_IP)),
    )
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    assert unit.public_address == "203.0.113.42"


def test_juju_unit_public_address_falls_back_to_private_address(monkeypatch):
    """public_address falls back to private_address when `public-address` is absent."""
    monkeypatch.setattr(
        "kube_galaxy.pkg.units.juju.run",
        lambda cmd, **kw: _make_run_result(stdout=json.dumps(_FULL_STATE)),
    )
    unit = JujuUnit("myapp/0", NodeRole.CONTROL_PLANE, 0)
    # private_address is a cached_property backed by run(); stub it directly
    monkeypatch.setattr(
        JujuUnit,
        "private_address",
        property(lambda self: "10.0.0.5"),
    )
    assert unit.public_address == "10.0.0.5"
