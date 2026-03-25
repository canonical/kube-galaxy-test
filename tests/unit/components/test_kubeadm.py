from unittest.mock import MagicMock

import yaml

from kube_galaxy.pkg.cluster_context import ClusterContext
from kube_galaxy.pkg.components.kubeadm import Kubeadm
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    NetworkConfig,
    RepoInfo,
)
from kube_galaxy.pkg.units._base import RunResult
from tests.unit.components.conftest import MockUnit


def test_kubeadm_configure_writes_cluster_config(arch_info, monkeypatch, tmp_path):
    # Build manifest with networking
    net = NetworkConfig(name="default", service_cidr="10.96.0.0/12", pod_cidr="192.168.0.0/16")
    manifest = Manifest(
        name="test",
        description="d",
        kubernetes_version="1.24",
        networking=[net],
    )

    repo = RepoInfo(base_url="https://github.com/kubernetes/kubernetes")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="https://example/{{ repo.base-url }}/{{ release }}/kubeadm",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    config = ComponentConfig(name="kubeadm", category="k8s", release="v1", installation=install)

    # Simulate `kubeadm config print init-defaults` returning two YAML docs
    docs = [
        {
            "kind": "InitConfiguration",
            "localAPIEndpoint": {"advertiseAddress": ""},
            "nodeRegistration": {"taints": []},
        },
        {"kind": "ClusterConfiguration", "networking": {}, "clusterName": ""},
    ]
    defaults_yaml = "".join(yaml.safe_dump(d) for d in docs)

    mock_unit = MockUnit()
    mock_unit.set_run_results(
        RunResult(0, defaults_yaml, ""),  # kubeadm config print init-defaults
        RunResult(0, "", ""),  # write_config_file: mkdir parent (kubelet conf)
        RunResult(0, "", ""),  # write_config_file: chmod (kubelet conf)
        RunResult(0, "", ""),  # write_config_file: mkdir parent (cluster config)
        RunResult(0, "", ""),  # write_config_file: chmod (cluster config)
    )

    comp = Kubeadm(ClusterContext(), manifest, config, arch_info)
    comp.unit = mock_unit

    # Provide a kubelet instance with an install_path so _which() succeeds
    class StubKubelet:
        install_path = "/usr/local/bin/kubelet"

    comp.components["kubelet"] = StubKubelet()

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

    # redirect staging root to test tmp_path to avoid cwd writes
    monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))

    comp.configure_hook()

    # After configure_hook, cluster config path should be set
    assert comp._cluster_config is not None
    # Verify the cluster config was pushed to the unit via put()
    assert any(str(comp._cluster_config) in str(dest) for _, dest in mock_unit.put_calls), (
        "expected unit.put() call for cluster config"
    )


class ComponentStub:
    def __init__(self, name, method: str, repo=None, tag=None, release=None):
        self.config = MagicMock()
        self.config.name = name
        self.config.release = release or "v1.0"
        self.config.installation.method = InstallMethod[method]
        self.image_repository = repo
        self.image_tag = tag


def _make_kubeadm_config() -> ComponentConfig:
    """Return a minimal ComponentConfig that passes _INSTALL_STRATEGIES validation."""
    repo = RepoInfo(base_url="https://github.com/kubernetes/kubernetes")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="https://example/{{ release }}/kubeadm",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    return ComponentConfig(name="kubeadm", category="k8s", release="v1", installation=install)
