from pathlib import Path

from kube_galaxy.pkg.components.kubelet import Kubelet
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
)


class ExampleResp:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_kubelet_configure_calls_urlopen_and_tee(monkeypatch, tmp_path):
    # Prepare minimal manifest/config
    manifest = Manifest(name="m", description="d", kubernetes_version="1.24")
    install = InstallConfig(
        method=InstallMethod.BINARY, source_format="https://example/{repo}/{release}/{arch}/kubelet"
    )
    config = ComponentConfig(
        name="kubelet", category="k8s", release="v1", repo="r", installation=install
    )

    comp = Kubelet({}, manifest, config)
    # set an install path so replace works
    comp.install_path = "/usr/local/bin/kubelet"

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))

        class R:
            stdout = ""

        return R()

    # Fake urlopen to return service content containing /usr/bin/kubelet
    monkeypatch.setattr(
        "kube_galaxy.pkg.components.kubelet.urlopen",
        lambda url: ExampleResp(b"ExecStart=/usr/bin/kubelet\n"),
    )
    monkeypatch.setattr("kube_galaxy.pkg.components.kubelet.run", fake_run)
    # Patch the base module run used by create_systemd_service
    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # redirect component temp dir to test tmp_path to avoid /opt writes
    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, name: Path(tmp_path) / name / "temp"),
    )

    # Call configure hook
    comp.configure_hook()

    # Expect cp to be called to copy temp service file to system location
    temp_service = Path(comp.component_tmp_dir) / "kubelet.service"
    assert any(cmd[:2] == ["sudo", "cp"] and str(temp_service) in cmd for cmd in calls)
