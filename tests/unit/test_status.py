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

    monkeypatch.setattr(status_cmd, "wait_for_nodes", fake_wait_for_nodes)
    monkeypatch.setattr(status_cmd, "wait_for_pods", fake_wait_for_pods)
    monkeypatch.setattr(status_cmd, "get_context", fake_get_context)
    monkeypatch.setattr(status_cmd, "get_nodes", fake_get_nodes)
    monkeypatch.setattr(status_cmd, "get_cluster_info", lambda _unit: "cluster-info")
    monkeypatch.setattr(status_cmd, "get_pods", lambda _unit: "pods-output")
    monkeypatch.setattr(status_cmd, "_check_command", lambda _cmd: "ok")
    monkeypatch.setattr(status_cmd.shutil, "which", lambda _cmd: "/usr/bin/tool")

    status_cmd.status(wait=True, timeout=123)

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

    monkeypatch.setattr(status_cmd, "wait_for_nodes", fake_wait_for_nodes)
    monkeypatch.setattr(status_cmd, "get_context", fake_get_context)
    monkeypatch.setattr(status_cmd, "get_nodes", fake_get_nodes)
    monkeypatch.setattr(status_cmd, "_check_command", lambda _cmd: "ok")
    monkeypatch.setattr(status_cmd.shutil, "which", lambda _cmd: "/usr/bin/tool")

    with pytest.raises(typer.Exit) as exc:
        status_cmd.status(wait=True, timeout=60)

    assert exc.value.exit_code == 1


def test_cli_status_forwards_wait_and_timeout(monkeypatch):
    captured: dict[str, int | bool] = {}

    def fake_status(wait: bool = False, timeout: int = 300):
        captured["wait"] = wait
        captured["timeout"] = timeout

    monkeypatch.setattr(cli.status, "status", fake_status)

    cli.status_cmd(wait=True, timeout=45)

    assert captured == {"wait": True, "timeout": 45}
