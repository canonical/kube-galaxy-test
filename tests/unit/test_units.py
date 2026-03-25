"""Unit tests for the units package: Unit ABC, LocalUnit."""

import zipfile
from pathlib import Path

import pytest

from kube_galaxy.pkg.units._base import RunResult, Unit
from kube_galaxy.pkg.units.local import LocalUnit
from kube_galaxy.pkg.units.lxdvm import LXDUnit
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError

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
    unit = LXDUnit("test-container")
    assert unit.name == "test-container"


def test_lxd_unit_implements_unit_abc():
    """LXDUnit has no unimplemented abstract methods — mypy/ABC compliant."""
    # If LXDUnit is missing any abstract method, this will raise TypeError
    unit = LXDUnit("abc")
    assert isinstance(unit, Unit)


# ---------------------------------------------------------------------------
# LocalUnit.enlist — no-op
# ---------------------------------------------------------------------------


def test_local_unit_enlist_is_noop():
    """LocalUnit.enlist() returns immediately without error."""
    u = LocalUnit()
    u.enlist()  # must not raise
    u.enlist(timeout=60)  # also no-op with explicit timeout


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

    unit = LXDUnit("test-vm")
    unit.enlist(timeout=30)

    # Only one lxc exec call was needed
    assert len(calls) == 3
    assert "hostname" in calls[0]


def test_lxd_unit_enlist_zero_timeout_succeeds_if_ready(monkeypatch):
    """enlist(timeout=0) returns immediately when agent responds."""

    def fake_run(cmd, **kwargs):
        return type("R", (), {"returncode": 0, "stdout": "my-host\n", "stderr": ""})()

    monkeypatch.setattr("kube_galaxy.pkg.units.lxdvm.subprocess.run", fake_run)

    unit = LXDUnit("test-vm")
    unit.enlist(timeout=0)  # must not raise


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

    unit = LXDUnit("test-vm")
    unit.enlist(timeout=60)

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

    unit = LXDUnit("test-vm")
    with pytest.raises(ClusterError, match="Timed out waiting for unit 'test-vm'"):
        unit.enlist(timeout=120)
