"""Tests for ArtifactServer and Unit.staging_url / set_artifact_server."""

import http.client
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import kube_galaxy.pkg.utils.artifact_server as artifact_server_mod
from kube_galaxy.pkg.cluster_context import ClusterContext
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.units.local import LocalUnit
from kube_galaxy.pkg.utils.artifact_server import ArtifactServer, detect_orchestrator_ip
from kube_galaxy.pkg.utils.components import install_binary
from tests.unit.components.conftest import MockUnit


def _ctx_with_server(base_url: str) -> ClusterContext:
    """Return a ClusterContext wired to a mock ArtifactServer at *base_url*."""
    server = MagicMock()
    server.base_url = base_url
    return ClusterContext(artifact_server=server)


# ---------------------------------------------------------------------------
# ArtifactServer — lifecycle
# ---------------------------------------------------------------------------


class TestArtifactServerLifecycle:
    def test_context_manager_starts_and_stops(self, monkeypatch, tmp_path):
        """ArtifactServer starts in __enter__ and stops in __exit__."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
        with ArtifactServer(port=18765, advertise_host="127.0.0.1") as srv:
            assert srv._server is not None
            assert srv._thread is not None
        assert srv._server is None
        assert srv._thread is None

    def test_start_stop_explicit(self, monkeypatch, tmp_path):
        """start() and stop() work without the context manager."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
        srv = ArtifactServer(port=18766, advertise_host="127.0.0.1")
        srv.start()
        try:
            assert srv._thread is not None and srv._thread.is_alive()
        finally:
            srv.stop()
        assert srv._server is None


# ---------------------------------------------------------------------------
# ArtifactServer — HTTP serving
# ---------------------------------------------------------------------------


class TestArtifactServerServing:
    def test_serves_file_from_staging_root(self, monkeypatch, tmp_path):
        """Files placed in staging_root() are reachable via HTTP."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))

        # Create a test file in the staging area
        content = b"hello artifact"
        file_rel = Path("opt/kube-galaxy/containerd/temp/containerd.tgz")
        file_path = tmp_path / file_rel
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

        port = 18767
        with ArtifactServer(port=port, advertise_host="127.0.0.1"):
            # Give the server a moment to bind
            time.sleep(0.1)
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", f"/{file_rel}")
            resp = conn.getresponse()
            assert resp.status == 200
            assert resp.read() == content

    def test_returns_404_for_missing_file(self, monkeypatch, tmp_path):
        """A GET for a non-existent file returns 404."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
        port = 18768
        with ArtifactServer(port=port, advertise_host="127.0.0.1"):
            time.sleep(0.1)
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/nonexistent/file.bin")
            resp = conn.getresponse()
            assert resp.status == 404


# ---------------------------------------------------------------------------
# ArtifactServer — url_for
# ---------------------------------------------------------------------------


class TestArtifactServerUrlFor:
    def test_url_for_returns_correct_url(self, monkeypatch, tmp_path):
        """url_for() forms the correct HTTP URL for a staged path."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
        srv = ArtifactServer(port=18769, advertise_host="10.0.0.1")
        staged = tmp_path / "opt/kube-galaxy/runc/temp/runc"
        url = srv.url_for(staged)
        assert url == "http://10.0.0.1:18769/opt/kube-galaxy/runc/temp/runc"

    def test_url_for_raises_for_path_outside_staging_root(self, monkeypatch, tmp_path):
        """url_for() raises ValueError if the path escapes staging_root()."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
        srv = ArtifactServer(port=18770, advertise_host="127.0.0.1")
        outside = Path("/etc/passwd")
        with pytest.raises(ValueError, match="not inside staging_root"):
            srv.url_for(outside)

    def test_base_url_property(self):
        """base_url uses the advertise_host and port."""
        srv = ArtifactServer(port=9876, advertise_host="192.168.1.50")
        assert srv.base_url == "http://192.168.1.50:9876"


# ---------------------------------------------------------------------------
# Unit.staging_url / set_artifact_server
# ---------------------------------------------------------------------------


class TestUnitStagingUrl:
    def test_staging_url_returns_file_uri_by_default(self, monkeypatch, tmp_path):
        """Without an artifact server, staging_url() returns a file:// URI."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
        unit = MockUnit()
        staged = tmp_path / "opt/kube-galaxy/kubelet/temp/kubelet"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(b"binary")

        url = unit.staging_url(staged)
        assert url.startswith("file://")
        assert "kubelet" in url

    def test_staging_url_returns_http_when_server_configured(self, monkeypatch, tmp_path):
        """After set_cluster_context(), staging_url() returns an HTTP URL."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
        unit = MockUnit()
        unit.set_cluster_context(_ctx_with_server("http://10.0.0.1:8765"))

        staged = tmp_path / "opt/kube-galaxy/kubelet/temp/kubelet"
        url = unit.staging_url(staged)
        assert url == "http://10.0.0.1:8765/opt/kube-galaxy/kubelet/temp/kubelet"

    def test_set_artifact_server_is_per_instance(self):
        """set_cluster_context() only affects the specific Unit instance."""
        u1 = MockUnit()
        u2 = MockUnit()
        ctx = _ctx_with_server("http://server:8765")
        u1.set_cluster_context(ctx)
        assert u1._ctx is ctx
        # u2 is not affected
        assert u2._ctx is None

    def test_staging_url_strips_trailing_slash_from_base(self, monkeypatch, tmp_path):
        """Trailing slash in base_url does not produce a double slash."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
        unit = MockUnit()
        unit.set_cluster_context(_ctx_with_server("http://10.0.0.1:8765/"))  # trailing slash

        staged = tmp_path / "opt/kube-galaxy/runc/temp/runc"
        url = unit.staging_url(staged)
        assert "//" not in url.replace("http://", "")

    def test_local_unit_staging_url_default_is_file_uri(self, monkeypatch, tmp_path):
        """LocalUnit.staging_url() returns file:// by default (no server needed)."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
        unit = LocalUnit()
        staged = tmp_path / "opt/kube-galaxy/kubectl/temp/kubectl"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(b"binary")

        url = unit.staging_url(staged)
        assert url.startswith("file:///")


# ---------------------------------------------------------------------------
# install_binary uses staging_url + download (not unit.put)
# ---------------------------------------------------------------------------


class TestInstallBinaryUsesDownload:
    def test_install_binary_calls_download_not_put(self, monkeypatch, tmp_path):
        """install_binary() uses unit.download() instead of unit.put()."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))

        unit = MockUnit()
        # Create a fake binary in staging
        comp_name = "mycomp"
        staged = tmp_path / "opt/kube-galaxy" / comp_name / "temp" / "mycomp"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(b"binary")

        install_binary(staged, "mycomp", comp_name, unit)

        # Should use download, not put
        assert not unit.put_calls, "install_binary must not call unit.put()"
        assert len(unit.download_calls) == 1

        url, dest = unit.download_calls[0]
        assert url.startswith("file://")
        assert "mycomp" in dest

    def test_install_binary_uses_http_url_when_server_configured(self, monkeypatch, tmp_path):
        """install_binary() uses the artifact server HTTP URL when configured."""
        monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))

        unit = MockUnit()
        unit.set_cluster_context(_ctx_with_server("http://192.168.1.1:8765"))

        comp_name = "mycomp"
        staged = tmp_path / "opt/kube-galaxy" / comp_name / "temp" / "mycomp"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(b"binary")

        install_binary(staged, "mycomp", comp_name, unit)

        assert not unit.put_calls, "install_binary must not call unit.put()"
        url, _ = unit.download_calls[0]
        assert url.startswith("http://192.168.1.1:8765/")


# ---------------------------------------------------------------------------
# detect_orchestrator_ip — module-level function
# ---------------------------------------------------------------------------


def test_detect_orchestrator_ip_returns_ip_string():
    """detect_orchestrator_ip() returns a non-empty IPv4-like string."""
    ip = detect_orchestrator_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0
    assert "." in ip  # basic IPv4 sanity check


def test_artifact_server_detect_ip_delegates_to_module_function(monkeypatch):
    """ArtifactServer.detect_ip delegates to the module-level detect_orchestrator_ip()."""
    monkeypatch.setattr(artifact_server_mod, "detect_orchestrator_ip", lambda: "1.2.3.4")
    srv = ArtifactServer(port=9999)
    assert srv.detect_ip == "1.2.3.4"
