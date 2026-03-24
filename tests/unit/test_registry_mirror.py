"""Tests for RegistryMirror."""

import os
import subprocess
from pathlib import Path

import pytest

import kube_galaxy.pkg.utils.registry_mirror as mirror_mod
from kube_galaxy.pkg.literals import SystemPaths, URLs
from kube_galaxy.pkg.manifest.models import RegistryConfig
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.registry_mirror import RegistryMirror, verify_prerequisites
from kube_galaxy.pkg.utils.shell import ShellError

_FAKE_IP = "10.0.0.1"


@pytest.fixture
def patched_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Patch detect_orchestrator_ip and staging_root for all mirror tests."""
    monkeypatch.setattr(mirror_mod, "detect_orchestrator_ip", lambda: _FAKE_IP)
    monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
    return tmp_path


def _noop_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


# ---------------------------------------------------------------------------
# verify_prerequisites
# ---------------------------------------------------------------------------


class TestVerifyPrerequisites:
    def test_passes_when_both_tools_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """verify_prerequisites() succeeds when docker and skopeo are on PATH."""

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"/usr/bin/{cmd[1]}", stderr="")

        monkeypatch.setattr(mirror_mod.shell, "run", fake_run)
        verify_prerequisites()  # must not raise

    def test_raises_cluster_error_when_docker_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """verify_prerequisites() raises ClusterError when docker is absent."""

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if cmd[1] == "docker":
                raise ShellError(cmd, 1, "not found")
            return subprocess.CompletedProcess(cmd, 0, stdout=f"/usr/bin/{cmd[1]}", stderr="")

        monkeypatch.setattr(mirror_mod.shell, "run", fake_run)
        with pytest.raises(ClusterError, match="docker"):
            verify_prerequisites()

    def test_raises_cluster_error_when_skopeo_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """verify_prerequisites() raises ClusterError when skopeo is absent."""

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if cmd[1] == "skopeo":
                raise ShellError(cmd, 1, "not found")
            return subprocess.CompletedProcess(cmd, 0, stdout=f"/usr/bin/{cmd[1]}", stderr="")

        monkeypatch.setattr(mirror_mod.shell, "run", fake_run)
        with pytest.raises(ClusterError, match="skopeo"):
            verify_prerequisites()

    def test_start_calls_verify_prerequisites(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """start() delegates to verify_prerequisites before launching docker."""
        verified: list[bool] = []
        monkeypatch.setattr(mirror_mod, "verify_prerequisites", lambda: verified.append(True))
        monkeypatch.setattr(mirror_mod.shell, "run", _noop_run)
        RegistryMirror(RegistryConfig()).start()
        assert verified == [True]


# ---------------------------------------------------------------------------
# RegistryMirror — properties
# ---------------------------------------------------------------------------


class TestRegistryMirrorProperties:
    def test_base_url_uses_ip_and_port(self, patched_env: Path) -> None:
        """base_url combines detected IP with configured port."""
        mirror = RegistryMirror(RegistryConfig(port=5000))
        assert mirror.base_url == f"http://{_FAKE_IP}:5000"

    def test_base_url_respects_custom_port(self, patched_env: Path) -> None:
        """base_url reflects a non-default port."""
        mirror = RegistryMirror(RegistryConfig(port=6000))
        assert mirror.base_url == f"http://{_FAKE_IP}:6000"

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
        cfg = RegistryConfig(remote_registry="registry.k8s.io", port=5000)
        RegistryMirror(cfg).start()

        assert len(calls) == 3  # which docker, which skopeo, docker run
        cmd = calls[-1]  # docker run is the last call
        assert cmd[:2] == ["docker", "run"]
        assert "-d" in cmd
        assert cmd[cmd.index("-p") + 1] == "5000:5000"
        assert cmd[cmd.index("--name") + 1] == "registry-cache"
        assert cmd[cmd.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
        assert not any("REGISTRY_PROXY_REMOTEURL" in arg for arg in cmd)
        assert cmd[-1] == "registry:2"


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
    def test_preload_pulls_matching_refs(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """preload() copies refs whose hostname matches cfg.remote_registry."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        mirror = RegistryMirror(RegistryConfig(remote_registry=URLs.REGISTRY_K8S_IO, port=5000))
        mirror.preload(
            [
                f"{URLs.REGISTRY_K8S_IO}/pause:3.10",
                f"{URLs.REGISTRY_K8S_IO}/etcd:3.5.0",
            ]
        )
        assert len(calls) == 2
        assert calls[0] == [
            "skopeo",
            "copy",
            "--all",
            "--dest-tls-verify=false",
            f"docker://{URLs.REGISTRY_K8S_IO}/pause:3.10",
            f"docker://{_FAKE_IP}:5000/pause:3.10",
        ]
        assert calls[1] == [
            "skopeo",
            "copy",
            "--all",
            "--dest-tls-verify=false",
            f"docker://{URLs.REGISTRY_K8S_IO}/etcd:3.5.0",
            f"docker://{_FAKE_IP}:5000/etcd:3.5.0",
        ]

    def test_preload_skips_non_matching_refs(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """preload() silently skips refs from other registries."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        mirror = RegistryMirror(RegistryConfig(remote_registry=URLs.REGISTRY_K8S_IO, port=5000))
        mirror.preload(
            [
                f"{URLs.REGISTRY_K8S_IO}/pause:3.10",
                "docker.io/library/ubuntu:22.04",
                "ghcr.io/org/image:latest",
            ]
        )
        assert len(calls) == 1
        assert calls[0] == [
            "skopeo",
            "copy",
            "--all",
            "--dest-tls-verify=false",
            f"docker://{URLs.REGISTRY_K8S_IO}/pause:3.10",
            f"docker://{_FAKE_IP}:5000/pause:3.10",
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
        mirror.preload([f"{URLs.REGISTRY_K8S_IO}/coredns/coredns:v1.10.1"])
        assert calls == [
            [
                "skopeo",
                "copy",
                "--all",
                "--dest-tls-verify=false",
                f"docker://{URLs.REGISTRY_K8S_IO}/coredns/coredns:v1.10.1",
                f"docker://{_FAKE_IP}:5000/coredns/coredns:v1.10.1",
            ]
        ]

    def test_preload_empty_list_is_noop(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """preload() with an empty list makes no skopeo calls."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        RegistryMirror(RegistryConfig()).preload([])
        assert calls == []

    def test_preload_docker_archive_tuple(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """preload() accepts (docker-archive:path, dest_path) tuples."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        tar = tmp_path / "etcd.tar"
        mirror = RegistryMirror(RegistryConfig(port=5000))
        mirror.preload([(f"docker-archive:{tar}", "etcd:3.5.0")])
        assert calls == [
            [
                "skopeo",
                "copy",
                "--all",
                "--dest-tls-verify=false",
                f"docker-archive:{tar}",
                f"docker://{_FAKE_IP}:5000/etcd:3.5.0",
            ]
        ]

    def test_preload_oci_archive_tuple(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """preload() accepts (oci-archive:path:tag, dest_path) tuples."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        tar = tmp_path / "pause.tar"
        mirror = RegistryMirror(RegistryConfig(port=5000))
        mirror.preload([(f"oci-archive:{tar}:pause:3.10", "pause:3.10")])
        assert calls == [
            [
                "skopeo",
                "copy",
                "--all",
                "--dest-tls-verify=false",
                f"oci-archive:{tar}:pause:3.10",
                f"docker://{_FAKE_IP}:5000/pause:3.10",
            ]
        ]

    def test_preload_mixed_registry_and_archive(
        self, patched_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """preload() handles a mix of registry refs and archive tuples."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            mirror_mod.shell, "run", lambda cmd, **kw: calls.append(cmd) or _noop_run(cmd)
        )
        tar = tmp_path / "etcd.tar"
        mirror = RegistryMirror(RegistryConfig(remote_registry=URLs.REGISTRY_K8S_IO, port=5000))
        mirror.preload(
            [
                f"{URLs.REGISTRY_K8S_IO}/pause:3.10",
                (f"docker-archive:{tar}", "etcd:3.5.0"),
            ]
        )
        assert len(calls) == 2
        assert calls[0][4] == f"docker://{URLs.REGISTRY_K8S_IO}/pause:3.10"
        assert calls[1][4] == f"docker-archive:{tar}"
        assert calls[1][5] == f"docker://{_FAKE_IP}:5000/etcd:3.5.0"


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
        assert calls[0][5] == f"docker://{_FAKE_IP}:6000/nginx:1.25"
        assert calls[0][6] == f"docker://{_FAKE_IP}:6000/nginx:1.25-custom"
