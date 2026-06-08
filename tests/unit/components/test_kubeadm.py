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
from kube_galaxy.pkg.utils.detector import get_arch_info
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

    # Fake requests.get used in configure_hook to fetch kubelet config
    mock_resp = MagicMock(text="/usr/bin/kubelet")
    monkeypatch.setattr(
        "kube_galaxy.pkg.components.kubeadm.requests.get", lambda url, **kw: mock_resp
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


def _make_kubeadm(
    manifest: Manifest | None = None,
    unit: MockUnit | None = None,
) -> Kubeadm:
    """Return a Kubeadm instance wired to a MockUnit."""
    if manifest is None:
        net = NetworkConfig(name="default", service_cidr="10.96.0.0/12", pod_cidr="192.168.0.0/16")
        manifest = Manifest(
            name="test",
            description="d",
            kubernetes_version="1.24",
            networking=[net],
        )
    comp = Kubeadm(ClusterContext(), manifest, _make_kubeadm_config(), get_arch_info("x86_64"))
    comp.unit = unit or MockUnit()
    return comp


# ---------------------------------------------------------------------------
# _update_cluster_config — certSANs injection
# ---------------------------------------------------------------------------


def test_update_cluster_config_injects_cert_sans(monkeypatch):
    """certSANs are populated with private address, public address, and hostname."""
    comp = _make_kubeadm()
    monkeypatch.setattr(type(comp.unit), "private_address", property(lambda self: "10.0.0.5"))
    monkeypatch.setattr(type(comp.unit), "public_address", property(lambda self: "203.0.113.42"))
    monkeypatch.setattr(type(comp.unit), "hostname", property(lambda self: "node-1"))

    config: dict = {"networking": {}, "clusterName": "", "apiServer": {}}
    comp._update_cluster_config(config)

    sans = config["apiServer"]["certSANs"]
    assert set(sans) == {"10.0.0.5", "203.0.113.42", "node-1"}


def test_update_cluster_config_deduplicates_cert_sans(monkeypatch):
    """certSANs deduplicates when public_address == private_address."""
    comp = _make_kubeadm()
    monkeypatch.setattr(type(comp.unit), "private_address", property(lambda self: "10.0.0.5"))
    monkeypatch.setattr(type(comp.unit), "public_address", property(lambda self: "10.0.0.5"))
    monkeypatch.setattr(type(comp.unit), "hostname", property(lambda self: "node-1"))

    config: dict = {"networking": {}, "clusterName": "", "apiServer": {}}
    comp._update_cluster_config(config)

    sans = config["apiServer"]["certSANs"]
    assert sans.count("10.0.0.5") == 1


def test_update_cluster_config_no_cert_sans_when_all_empty(monkeypatch):
    """certSANs key is not set when all address properties return empty strings."""
    comp = _make_kubeadm()
    monkeypatch.setattr(type(comp.unit), "private_address", property(lambda self: ""))
    monkeypatch.setattr(type(comp.unit), "public_address", property(lambda self: ""))
    monkeypatch.setattr(type(comp.unit), "hostname", property(lambda self: ""))

    config: dict = {"networking": {}, "clusterName": ""}
    comp._update_cluster_config(config)

    assert "certSANs" not in config.get("apiServer", {})


# ---------------------------------------------------------------------------
# pull_kubeconfig — server URL rewrite delegation
# ---------------------------------------------------------------------------


def test_pull_kubeconfig_calls_rewrite_when_public_address_set(monkeypatch, tmp_path):
    """pull_kubeconfig calls rewrite_cluster_server with the unit's public_address."""
    comp = _make_kubeadm()
    monkeypatch.setattr(type(comp.unit), "public_address", property(lambda self: "203.0.113.42"))

    local_cfg = tmp_path / "admin.conf"
    local_cfg.write_text("")

    monkeypatch.setattr(
        "kube_galaxy.pkg.components.kubeadm.SystemPaths.local_kube_config",
        classmethod(lambda cls: local_cfg),
    )
    monkeypatch.setattr(
        "kube_galaxy.pkg.components.kubeadm.SystemPaths.kube_config",
        classmethod(lambda cls: tmp_path / "config"),
    )
    monkeypatch.setattr("kube_galaxy.pkg.components.kubeadm.ensure_dir", lambda p: None)

    rewrite_calls: list[tuple] = []
    monkeypatch.setattr(
        "kube_galaxy.pkg.components.kubeadm.rewrite_cluster_server",
        lambda path, host: rewrite_calls.append((path, host)),
    )

    comp.pull_kubeconfig()

    assert rewrite_calls == [(local_cfg, "203.0.113.42")]


def test_pull_kubeconfig_skips_rewrite_when_public_address_empty(monkeypatch, tmp_path):
    """pull_kubeconfig skips rewrite_cluster_server when public_address is empty."""
    comp = _make_kubeadm()
    monkeypatch.setattr(type(comp.unit), "public_address", property(lambda self: ""))

    local_cfg = tmp_path / "admin.conf"
    local_cfg.write_text("")

    monkeypatch.setattr(
        "kube_galaxy.pkg.components.kubeadm.SystemPaths.local_kube_config",
        classmethod(lambda cls: local_cfg),
    )
    monkeypatch.setattr(
        "kube_galaxy.pkg.components.kubeadm.SystemPaths.kube_config",
        classmethod(lambda cls: tmp_path / "config"),
    )
    monkeypatch.setattr("kube_galaxy.pkg.components.kubeadm.ensure_dir", lambda p: None)

    rewrite_calls: list[tuple] = []
    monkeypatch.setattr(
        "kube_galaxy.pkg.components.kubeadm.rewrite_cluster_server",
        lambda path, host: rewrite_calls.append((path, host)),
    )

    comp.pull_kubeconfig()

    assert rewrite_calls == []
