import pytest
import typer

from kube_galaxy import cli
from kube_galaxy.cmd import status as status_cmd
from kube_galaxy.pkg.utils.errors import ClusterError


def test_status_wait_runs_readiness_checks(monkeypatch):
    """Test that status with --wait runs node and pod readiness checks."""
    wait_for_nodes_called = []
    wait_for_pods_called = []

    def fake_wait_for_nodes(_unit, timeout=300, condition="Ready"):
        wait_for_nodes_called.append({"timeout": timeout, "condition": condition})

    def fake_wait_for_pods(_unit, namespace="kube-system", timeout=300, condition="Ready"):
        wait_for_pods_called.append(
            {"namespace": namespace, "timeout": timeout, "condition": condition}
        )

    def fake_get_context(_unit):
        return "test-context"

    def fake_get_nodes(_unit):
        return "NAME STATUS ROLES AGE VERSION\nnode-1 Ready control-plane 1m v1.36.0\n"

    fake_unit = object()
    fake_provider = type("P", (), {"locate": lambda self, *a: fake_unit})()

    monkeypatch.setattr(status_cmd, "wait_for_nodes", fake_wait_for_nodes)
    monkeypatch.setattr(status_cmd, "wait_for_pods", fake_wait_for_pods)
    monkeypatch.setattr(status_cmd, "get_context", fake_get_context)
    monkeypatch.setattr(status_cmd, "get_nodes", fake_get_nodes)
    monkeypatch.setattr(status_cmd, "get_cluster_info", lambda _unit: "cluster-info")
    monkeypatch.setattr(status_cmd, "get_pods", lambda _unit: "pods-output")
    monkeypatch.setattr(status_cmd, "_check_command", lambda _cmd: "ok")
    monkeypatch.setattr(status_cmd.shutil, "which", lambda _cmd: "/usr/bin/tool")
    monkeypatch.setattr(
        status_cmd,
        "load_manifest",
        lambda _path: type("M", (), {"name": "test"})(),
    )
    monkeypatch.setattr(status_cmd, "provider_factory", lambda _manifest: fake_provider)

    status_cmd.status("dummy.yaml", wait=True, timeout=123)

    assert len(wait_for_nodes_called) == 1
    assert wait_for_nodes_called[0]["timeout"] == 123
    assert len(wait_for_pods_called) == 1
    assert wait_for_pods_called[0]["timeout"] == 123
    assert wait_for_pods_called[0]["namespace"] == "kube-system"


def test_status_wait_exits_non_zero_on_readiness_failure(monkeypatch):
    """Test that status exits with error code on readiness failure."""

    def fake_wait_for_nodes(_unit, timeout=300, condition="Ready"):
        raise ClusterError("timed out waiting for node readiness")

    def fake_get_context(_unit):
        return "test-context"

    def fake_get_nodes(_unit):
        return "NAME STATUS ROLES AGE VERSION\nnode-1 Ready control-plane 1m v1.36.0\n"

    fake_unit = object()
    fake_provider = type("P", (), {"locate": lambda self, *a: fake_unit})()

    monkeypatch.setattr(status_cmd, "wait_for_nodes", fake_wait_for_nodes)
    monkeypatch.setattr(status_cmd, "get_context", fake_get_context)
    monkeypatch.setattr(status_cmd, "get_nodes", fake_get_nodes)
    monkeypatch.setattr(status_cmd, "_check_command", lambda _cmd: "ok")
    monkeypatch.setattr(status_cmd.shutil, "which", lambda _cmd: "/usr/bin/tool")
    monkeypatch.setattr(
        status_cmd,
        "load_manifest",
        lambda _path: type("M", (), {"name": "test"})(),
    )
    monkeypatch.setattr(status_cmd, "provider_factory", lambda _manifest: fake_provider)

    with pytest.raises(typer.Exit) as exc:
        status_cmd.status("dummy.yaml", wait=True, timeout=60)

    assert exc.value.exit_code == 1


def test_cli_status_forwards_wait_and_timeout(monkeypatch):
    captured: dict[str, object] = {}

    def fake_status(manifest_path: str, wait: bool = False, timeout: int = 300) -> None:
        captured["manifest_path"] = manifest_path
        captured["wait"] = wait
        captured["timeout"] = timeout

    monkeypatch.setattr(cli.status, "status", fake_status)
    monkeypatch.setattr(cli, "_resolve_manifest", lambda _m: "manifests/test.yaml")

    cli.status_cmd(wait=True, timeout=45)

    assert captured["manifest_path"] == "manifests/test.yaml"
    assert captured["wait"] is True
    assert captured["timeout"] == 45


def test_status_shows_active_manifest():
    """_print_active_manifest shows the resolved manifest path when given."""
    # Should not raise; just verifying the branch executes without error
    status_cmd._print_active_manifest("/some/path/baseline.yaml")


def test_status_shows_warning_when_no_active_manifest():
    """_print_active_manifest shows a warning when given None."""
    # Should not raise; just verifying the warning branch executes without error
    status_cmd._print_active_manifest(None)


def test_cli_resolve_manifest_uses_explicit_value():
    """_resolve_manifest returns the explicit manifest string as-is."""
    result = cli._resolve_manifest("manifests/my.yaml")
    assert result == "manifests/my.yaml"


def test_cli_resolve_manifest_falls_back_to_active(tmp_path, monkeypatch):
    """_resolve_manifest falls back to the active manifest link when none given."""
    active = tmp_path / "baseline.yaml"
    active.write_text("name: test\n")
    monkeypatch.setattr(cli, "get_active_manifest", lambda: active)

    result = cli._resolve_manifest(None)
    assert result == str(active)


def test_cli_resolve_manifest_exits_when_no_manifest(tmp_path, monkeypatch):
    """_resolve_manifest exits with code 1 when no manifest and no active link."""
    monkeypatch.setattr(cli, "get_active_manifest", lambda: None)

    with pytest.raises(typer.Exit) as exc:
        cli._resolve_manifest(None)

    assert exc.value.exit_code == 1
