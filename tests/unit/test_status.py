from types import SimpleNamespace

import pytest
import typer

from kube_galaxy import cli
from kube_galaxy.cmd import status as status_cmd
from kube_galaxy.pkg.utils.shell import ShellError


def test_status_wait_runs_readiness_checks(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):
        calls.append(command)

        if command[:3] == ["kubectl", "config", "current-context"]:
            return SimpleNamespace(returncode=0, stdout="test-context\n", stderr="")
        if command[:3] == ["kubectl", "get", "nodes"] and "-o" not in command:
            return SimpleNamespace(
                returncode=0,
                stdout="NAME STATUS ROLES AGE VERSION\nnode-1 Ready control-plane 1m v1.36.0\n",
                stderr="",
            )

        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(status_cmd, "run", fake_run)
    monkeypatch.setattr(status_cmd, "_check_command", lambda _cmd: "ok")
    monkeypatch.setattr(status_cmd.shutil, "which", lambda _cmd: "/usr/bin/tool")

    status_cmd.status(wait=True, timeout=123)

    assert [
        "kubectl",
        "wait",
        "--for=condition=Ready",
        "node",
        "--all",
        "--timeout=123s",
    ] in calls
    assert [
        "kubectl",
        "wait",
        "--for=condition=Ready",
        "pod",
        "--all",
        "-n",
        "kube-system",
        "--timeout=123s",
    ] in calls


def test_status_wait_exits_non_zero_on_readiness_failure(monkeypatch):
    def fake_run(command: list[str], **_kwargs):
        if command[:5] == ["kubectl", "wait", "--for=condition=Ready", "node", "--all"]:
            raise ShellError(command, 1, "timed out waiting for node readiness")

        if command[:3] == ["kubectl", "config", "current-context"]:
            return SimpleNamespace(returncode=0, stdout="test-context\n", stderr="")

        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(status_cmd, "run", fake_run)
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
