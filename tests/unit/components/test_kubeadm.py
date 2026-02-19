from pathlib import Path

import yaml

from kube_galaxy.pkg.components.kubeadm import Kubeadm
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    NetworkConfig,
    NodeConfig,
)


class FakeCompleted:
    def __init__(self, stdout: str = ""):
        self.stdout = stdout


def test_kubeadm_configure_writes_cluster_config(monkeypatch, tmp_path):
    # Build manifest with networking
    net = NetworkConfig(name="default", service_cidr="10.96.0.0/12", pod_cidr="192.168.0.0/16")
    manifest = Manifest(
        name="test",
        description="d",
        kubernetes_version="1.24",
        nodes=NodeConfig(),
        networking=[net],
    )

    install = InstallConfig(
        method=InstallMethod.BINARY, source_format="https://example/{repo}/{release}/kubeadm"
    )
    config = ComponentConfig(
        name="kubeadm", category="k8s", release="v1", repo="r", installation=install
    )

    comp = Kubeadm({}, manifest, config)

    # Provide a kubelet instance with an install_path so _which() succeeds
    class StubKubelet:
        install_path = "/usr/local/bin/kubelet"

    comp.instances["kubelet"] = StubKubelet()

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        # Simulate `kubeadm config print init-defaults` returning two YAML docs
        if cmd and isinstance(cmd, list) and "kubeadm" in cmd[0] and "print" in cmd:
            docs = [
                {"kind": "InitConfiguration", "localAPIEndpoint": {"advertiseAddress": ""}},
                {"kind": "ClusterConfiguration", "networking": {}, "clusterName": ""},
            ]
            return FakeCompleted("".join(yaml.safe_dump(d) for d in docs))
        return FakeCompleted()

    # Fake urlopen used in configure_hook to fetch kubelet config
    class StubResp:
        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "kube_galaxy.pkg.components.kubeadm.urlopen", lambda url: StubResp(b"/usr/bin/kubelet")
    )
    # Patch both the module-local run and the base module run used by utility methods
    monkeypatch.setattr("kube_galaxy.pkg.components.kubeadm.run", fake_run)
    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # redirect component temp dir to test tmp_path to avoid /opt writes
    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, name: Path(tmp_path) / name / "temp"),
    )

    comp.configure_hook()

    # After configure_hook, cluster config path should be set
    assert comp._cluster_config is not None
    # The implementation may write the config via tee or copy; accept either
    assert any(
        (cmd[:2] == ["sudo", "tee"] or cmd[:2] == ["sudo", "cp"])
        and str(comp._cluster_config) in cmd
        for cmd in calls
    )
