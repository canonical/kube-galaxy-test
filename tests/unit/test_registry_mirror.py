"""Tests for RegistryMirror."""

import subprocess
from pathlib import Path

import pytest
import requests

import kube_galaxy.pkg.utils.registry_mirror as mirror_mod
from kube_galaxy.pkg.literals import SystemPaths, URLs
from kube_galaxy.pkg.manifest.models import RegistryConfig
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.registry_mirror import RegistryMirror, _print_dependency_status

_FAKE_IP = "10.0.0.1"


@pytest.fixture
def patched_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Patch detect_ip and staging_root for all mirror tests."""
    monkeypatch.setattr(mirror_mod, "detect_ip", lambda: _FAKE_IP)
    monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
    return tmp_path


def _noop_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


class _OkResponse:
    """Minimal fake HTTP response with ``ok = True``."""

    ok = True


# ---------------------------------------------------------------------------
# _print_dependency_status
# ---------------------------------------------------------------------------


class TestVerifyPrerequisites:
    def test_passes_when_both_tools_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_print_dependency_status() succeeds when docker and skopeo are on PATH."""

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"/usr/bin/{cmd[1]}", stderr="")

        monkeypatch.setattr(mirror_mod.shell, "run", fake_run)
        _print_dependency_status()  # must not raise

    def test_raises_cluster_error_when_docker_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_print_dependency_status() raises ClusterError when docker is absent."""

        def fake_which(cmd: str) -> str | None:
            if cmd == "docker":
                return None
            return f"/usr/bin/{cmd}"

        monkeypatch.setattr(mirror_mod.shell.shutil, "which", fake_which)
        with pytest.raises(ClusterError, match="docker"):
            _print_dependency_status()

    def test_raises_cluster_error_when_skopeo_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_print_dependency_status() raises ClusterError when skopeo is absent."""

        def fake_which(cmd: str) -> str | None:
            if cmd == "skopeo":
                return None
            return f"/usr/bin/{cmd}"

        monkeypatch.setattr(mirror_mod.shell.shutil, "which", fake_which)
        monkeypatch.setattr(mirror_mod.shell, "run", _noop_run)
        with pytest.raises(ClusterError, match="skopeo"):
            _print_dependency_status()

    def test_start_calls_print_dependency_status(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """start() delegates to _print_dependency_status before launching docker."""
        verified: list[bool] = []
        monkeypatch.setattr(mirror_mod, "_print_dependency_status", lambda: verified.append(True))
        monkeypatch.setattr(mirror_mod.shell, "run", _noop_run)
        monkeypatch.setattr(mirror_mod.requests, "get", lambda *a, **kw: _OkResponse())
        RegistryMirror(RegistryConfig()).start()
        assert verified == [True]


# ---------------------------------------------------------------------------
# RegistryMirror — properties
# ---------------------------------------------------------------------------


class TestRegistryMirrorProperties:
    def test_base_url_uses_ip_and_port(self, patched_env: Path) -> None:
        """base_url combines detected IP with configured port."""
        mirror = RegistryMirror(RegistryConfig(port=5000))
        assert mirror.registry_address(local=True) == f"{_FAKE_IP}:5000"

    def test_base_url_respects_custom_port(self, patched_env: Path) -> None:
        """base_url reflects a non-default port."""
        mirror = RegistryMirror(RegistryConfig(port=6000))
        assert mirror.registry_address(local=True) == f"{_FAKE_IP}:6000"

    def test_data_dir_is_under_staging_root(self, patched_env: Path, tmp_path: Path) -> None:
        """data_dir is always staging_root()/registry/data."""
        mirror = RegistryMirror(RegistryConfig())
        assert mirror.data_dir == tmp_path / "registry" / "data"


# ---------------------------------------------------------------------------
# RegistryMirror — start
# ---------------------------------------------------------------------------


class TestRegistryMirrorStart:
    def test_start_creates_data_dir(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """start() creates data_dir before launching the container."""
        monkeypatch.setattr(mirror_mod.shell, "run", _noop_run)
        monkeypatch.setattr(mirror_mod.requests, "get", lambda *a, **kw: _OkResponse())
        RegistryMirror(RegistryConfig()).start()
        assert (tmp_path / "registry" / "data").is_dir()

    def test_start_calls_docker_run_with_correct_flags(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """start() invokes docker run with the expected arguments."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        monkeypatch.setattr(mirror_mod.requests, "get", lambda *a, **kw: _OkResponse())
        cfg = RegistryConfig(remote_registry="registry.k8s.io", port=5000)
        RegistryMirror(cfg).start()

        assert len(calls) == 3  # which docker, which skopeo, docker run
        cmd = calls[-1]  # docker run is the last call
        assert cmd[:2] == ["docker", "run"]
        assert "-d" in cmd
        assert cmd[cmd.index("-p") + 1] == "5000:5000"
        assert cmd[cmd.index("--name") + 1] == "registry-cache"
        assert "--user" not in cmd  # registry container runs as root
        assert not any("REGISTRY_PROXY_REMOTEURL" in arg for arg in cmd)
        assert cmd[-1] == "registry:3"


# ---------------------------------------------------------------------------
# RegistryMirror — _wait_for_registry
# ---------------------------------------------------------------------------


class TestWaitForRegistry:
    def test_returns_immediately_when_ready(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_wait_for_registry() returns without error when /v2/ responds ok."""
        monkeypatch.setattr(mirror_mod.requests, "get", lambda *a, **kw: _OkResponse())
        RegistryMirror(RegistryConfig(port=5000))._wait_for_registry()  # must not raise

    def test_polls_correct_url(self, patched_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """_wait_for_registry() polls http://localhost:{port}/v2/."""
        polled: list[str] = []

        def fake_get(url: str, **kw: object) -> _OkResponse:
            polled.append(url)
            return _OkResponse()

        monkeypatch.setattr(mirror_mod.requests, "get", fake_get)
        RegistryMirror(RegistryConfig(port=5000))._wait_for_registry()
        assert polled == ["http://localhost:5000/v2/"]

    def test_retries_after_connection_error_then_succeeds(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_wait_for_registry() retries on ConnectionError and succeeds when ready."""
        attempts = [0]

        def fake_get(url: str, **kw: object) -> _OkResponse:
            attempts[0] += 1
            if attempts[0] < 3:
                raise requests.ConnectionError("connection refused")
            return _OkResponse()

        monkeypatch.setattr(mirror_mod.requests, "get", fake_get)
        monkeypatch.setattr(mirror_mod.time, "sleep", lambda _: None)
        RegistryMirror(RegistryConfig(port=5000))._wait_for_registry()
        assert attempts[0] == 3

    def test_raises_cluster_error_when_timeout_exceeded(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_wait_for_registry() raises ClusterError when the deadline passes."""
        monkeypatch.setattr(
            mirror_mod.requests,
            "get",
            lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("refused")),
        )
        monkeypatch.setattr(mirror_mod.time, "sleep", lambda _: None)
        with pytest.raises(ClusterError, match="Registry did not become ready"):
            RegistryMirror(RegistryConfig(port=5000))._wait_for_registry(timeout=0)

    def test_start_calls_wait_for_registry(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """start() calls _wait_for_registry() after docker run."""
        waited: list[bool] = []
        monkeypatch.setattr(mirror_mod.shell, "run", _noop_run)
        monkeypatch.setattr(
            RegistryMirror, "_wait_for_registry", lambda self, **kw: waited.append(True)
        )
        RegistryMirror(RegistryConfig()).start()
        assert waited == [True]


# ---------------------------------------------------------------------------
# RegistryMirror — stop
# ---------------------------------------------------------------------------


class TestRegistryMirrorStop:
    def test_stop_calls_docker_rm_force(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stop() calls docker rm -f on the named container."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        RegistryMirror(RegistryConfig()).stop()
        assert calls == [["docker", "rm", "-f", "registry-cache"]]


# ---------------------------------------------------------------------------
# RegistryMirror — preload
# ---------------------------------------------------------------------------


class TestRegistryMirrorPreload:
    def test_preload_copies_docker_ref_to_mirror(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """preload() copies a docker:// ref to the local mirror at mirror_path."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        mirror = RegistryMirror(RegistryConfig(port=5000))
        mirror.preload(
            f"docker://{URLs.REGISTRY_K8S_IO}/pause:3.10",
            "pause:3.10",
        )
        assert calls == [
            [
                "skopeo",
                "copy",
                "--all",
                "--quiet",
                "--dest-tls-verify=false",
                f"docker://{URLs.REGISTRY_K8S_IO}/pause:3.10",
                f"docker://{_FAKE_IP}:5000/pause:3.10",
            ]
        ]

    def test_preload_handles_nested_image_paths(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """preload() preserves nested path components (e.g. coredns/coredns)."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        mirror = RegistryMirror(RegistryConfig(remote_registry=URLs.REGISTRY_K8S_IO, port=5000))
        mirror.preload(
            f"docker://{URLs.REGISTRY_K8S_IO}/coredns/coredns:v1.10.1",
            "coredns/coredns:v1.10.1",
        )
        assert calls == [
            [
                "skopeo",
                "copy",
                "--all",
                "--quiet",
                "--dest-tls-verify=false",
                f"docker://{URLs.REGISTRY_K8S_IO}/coredns/coredns:v1.10.1",
                f"docker://{_FAKE_IP}:5000/coredns/coredns:v1.10.1",
            ]
        ]

    def test_preload_docker_archive(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """preload() accepts a docker-archive source ref."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        tar = tmp_path / "etcd.tar"
        mirror = RegistryMirror(RegistryConfig(port=5000))
        mirror.preload(f"docker-archive:{tar}", "etcd:3.5.0")
        assert calls == [
            [
                "skopeo",
                "copy",
                "--all",
                "--quiet",
                "--dest-tls-verify=false",
                f"docker-archive:{tar}",
                f"docker://{_FAKE_IP}:5000/etcd:3.5.0",
            ]
        ]

    def test_preload_oci_archive(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """preload() accepts an oci-archive source ref."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        tar = tmp_path / "pause.tar"
        mirror = RegistryMirror(RegistryConfig(port=5000))
        mirror.preload(f"oci-archive:{tar}:pause:3.10", "pause:3.10")
        assert calls == [
            [
                "skopeo",
                "copy",
                "--all",
                "--quiet",
                "--dest-tls-verify=false",
                f"oci-archive:{tar}:pause:3.10",
                f"docker://{_FAKE_IP}:5000/pause:3.10",
            ]
        ]

    def test_preload_called_twice_for_mixed_sources(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Two preload() calls (registry + archive) each issue one skopeo copy."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        tar = tmp_path / "etcd.tar"
        mirror = RegistryMirror(RegistryConfig(remote_registry=URLs.REGISTRY_K8S_IO, port=5000))
        mirror.preload(
            f"docker://{URLs.REGISTRY_K8S_IO}/pause:3.10",
            "pause:3.10",
        )
        mirror.preload(
            f"docker-archive:{tar}",
            "etcd:3.5.0",
        )
        assert len(calls) == 2
        assert calls[0][5] == f"docker://{URLs.REGISTRY_K8S_IO}/pause:3.10"
        assert calls[1][5] == f"docker-archive:{tar}"
        assert calls[1][6] == f"docker://{_FAKE_IP}:5000/etcd:3.5.0"


# ---------------------------------------------------------------------------
# RegistryMirror — retag
# ---------------------------------------------------------------------------


class TestRegistryMirrorRetag:
    def test_retag_copies_within_local_registry(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """retag() issues a skopeo copy from src to dst within the local registry."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        RegistryMirror(RegistryConfig(port=5000)).retag("pause:3.10", "pause:3.10-arm64")
        assert calls == [
            [
                "skopeo",
                "copy",
                "--all",
                "--quiet",
                "--src-tls-verify=false",
                "--dest-tls-verify=false",
                f"docker://{_FAKE_IP}:5000/pause:3.10",
                f"docker://{_FAKE_IP}:5000/pause:3.10-arm64",
            ]
        ]

    def test_retag_preserves_nested_paths(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """retag() preserves nested path components in src and dst."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        RegistryMirror(RegistryConfig(port=5000)).retag(
            "coredns/coredns:v1.10.1", "coredns/coredns:v1.10.1-amd64"
        )
        assert calls == [
            [
                "skopeo",
                "copy",
                "--all",
                "--quiet",
                "--src-tls-verify=false",
                "--dest-tls-verify=false",
                f"docker://{_FAKE_IP}:5000/coredns/coredns:v1.10.1",
                f"docker://{_FAKE_IP}:5000/coredns/coredns:v1.10.1-amd64",
            ]
        ]

    def test_retag_respects_custom_port(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """retag() uses the configured port in both src and dst addresses."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        RegistryMirror(RegistryConfig(port=6000)).retag("nginx:1.25", "nginx:1.25-custom")
        assert calls[0][6] == f"docker://{_FAKE_IP}:6000/nginx:1.25"
        assert calls[0][7] == f"docker://{_FAKE_IP}:6000/nginx:1.25-custom"


# ---------------------------------------------------------------------------
# RegistryMirror — inspect
# ---------------------------------------------------------------------------


class TestRegistryMirrorInspect:
    def test_inspect_returns_name_without_registry_prefix(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """inspect() strips the registry hostname and returns the image path."""
        tar = tmp_path / "pause.tar"
        payload = '{"Name": "registry.k8s.io/pause:3.10"}'
        monkeypatch.setattr(
            mirror_mod.shell,
            "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=payload, stderr=""),
        )
        result = RegistryMirror(RegistryConfig()).inspect(f"docker-archive:{tar}")
        assert result == "pause:3.10"

    def test_inspect_preserves_nested_path(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """inspect() keeps nested path components after stripping the registry host."""
        tar = tmp_path / "coredns.tar"
        payload = '{"Name": "registry.k8s.io/coredns/coredns:v1.11.1"}'
        monkeypatch.setattr(
            mirror_mod.shell,
            "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=payload, stderr=""),
        )
        result = RegistryMirror(RegistryConfig()).inspect(f"docker-archive:{tar}")
        assert result == "coredns/coredns:v1.11.1"

    def test_inspect_returns_empty_string_when_name_absent(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """inspect() returns '' when the JSON has no Name field."""
        tar = tmp_path / "unknown.tar"
        monkeypatch.setattr(
            mirror_mod.shell,
            "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr=""),
        )
        result = RegistryMirror(RegistryConfig()).inspect(f"docker-archive:{tar}")
        assert result == ""

    def test_inspect_calls_skopeo_inspect(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """inspect() invokes skopeo inspect with the supplied image_ref."""
        tar = tmp_path / "etcd.tar"
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell,
            "run",
            lambda cmd, **kw: (
                calls.append(cmd)
                or subprocess.CompletedProcess(cmd, 0, stdout='{"Name": "etcd:3.5.0"}', stderr="")
            ),
        )
        RegistryMirror(RegistryConfig()).inspect(f"docker-archive:{tar}")
        assert calls == [["skopeo", "inspect", f"docker-archive:{tar}"]]


# ---------------------------------------------------------------------------
# RegistryMirror — _skopeo_copy (--src-creds for ghcr.io)
# ---------------------------------------------------------------------------


class TestSkopeoCopy:
    def test_src_creds_added_for_ghcr_when_credentials_set(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_skopeo_copy includes --src-creds for ghcr.io sources when credentials are set."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        monkeypatch.setattr(mirror_mod, "GITHUB_ACTOR", "testuser")
        monkeypatch.setattr(mirror_mod, "GITHUB_TOKEN", "testtoken")

        mirror = RegistryMirror(RegistryConfig(port=5000))
        mirror._skopeo_copy(
            "docker://ghcr.io/canonical/mx-tool:v1.0.0",
            f"docker://{_FAKE_IP}:5000/canonical/mx-tool:v1.0.0",
        )

        assert len(calls) == 1
        cmd = calls[0]
        assert "--src-creds" in cmd
        creds_idx = cmd.index("--src-creds")
        assert cmd[creds_idx + 1] == "testuser:testtoken"

    def test_src_creds_not_added_for_non_ghcr_source(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_skopeo_copy does NOT include --src-creds for non-ghcr.io sources."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        monkeypatch.setattr(mirror_mod, "GITHUB_ACTOR", "testuser")
        monkeypatch.setattr(mirror_mod, "GITHUB_TOKEN", "testtoken")

        mirror = RegistryMirror(RegistryConfig(port=5000))
        mirror._skopeo_copy(
            "docker://registry.k8s.io/pause:3.10",
            f"docker://{_FAKE_IP}:5000/pause:3.10",
        )

        assert "--src-creds" not in calls[0]

    def test_src_creds_not_added_when_credentials_absent(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_skopeo_copy does NOT include --src-creds when GITHUB_ACTOR/TOKEN are unset."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        monkeypatch.setattr(mirror_mod, "GITHUB_ACTOR", None)
        monkeypatch.setattr(mirror_mod, "GITHUB_TOKEN", None)

        mirror = RegistryMirror(RegistryConfig(port=5000))
        mirror._skopeo_copy(
            "docker://ghcr.io/canonical/mx-tool:v1.0.0",
            f"docker://{_FAKE_IP}:5000/canonical/mx-tool:v1.0.0",
        )

        assert "--src-creds" not in calls[0]
