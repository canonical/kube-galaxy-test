"""Unit tests for helm install method."""


import pytest

from kube_galaxy.pkg.cluster_context import ClusterContext
from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    RepoInfo,
)
from kube_galaxy.pkg.units._base import RunResult
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.shell import ShellError
from tests.unit.components.conftest import MockUnit


@pytest.fixture
def manifest():
    """Create a minimal manifest for testing."""
    return Manifest(name="test-cluster", description="Test", kubernetes_version="1.35.0")


@pytest.fixture
def helm_repo_config():
    """Create a component config with helm_repo=True (repo-based install)."""
    repo = RepoInfo(base_url="https://docs.tigera.io/calico/charts")
    install = InstallConfig(
        method=InstallMethod.HELM,
        source_format="projectcalico/tigera-operator",
        bin_path="",
        repo=repo,
        retag_format="",
        helm_repo=True,
    )
    return ComponentConfig(
        name="calico",
        category="projectcalico/calico",
        release="3.30.6",
        installation=install,
    )


@pytest.fixture
def helm_archive_config():
    """Create a component config with helm_repo=False (archive-based install)."""
    repo = RepoInfo(base_url="https://github.com/org/chart")
    install = InstallConfig(
        method=InstallMethod.HELM,
        source_format=(
            "https://github.com/org/chart/releases/download/"
            "v{{ release }}/chart-{{ release }}.tgz"
        ),
        bin_path="",
        repo=repo,
        retag_format="",
        helm_repo=False,
    )
    return ComponentConfig(
        name="my-chart",
        category="org/chart",
        release="1.2.3",
        installation=install,
    )


@pytest.fixture
def helm_repo_component(manifest, arch_info, helm_repo_config, monkeypatch, tmp_path):
    """ComponentBase with helm_repo=True."""
    monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
    return ComponentBase(ClusterContext(), manifest, helm_repo_config, arch_info)


@pytest.fixture
def helm_archive_component(manifest, arch_info, helm_archive_config, monkeypatch, tmp_path):
    """ComponentBase with helm_repo=False."""
    monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
    return ComponentBase(ClusterContext(), manifest, helm_archive_config, arch_info)


# --- download hook tests ---


def test_download_skips_when_helm_repo(helm_repo_component, monkeypatch):
    """When helm_repo=True, download_hook does not download anything."""
    download_calls = []

    def fake_download_file(url, dest):
        download_calls.append((url, dest))

    monkeypatch.setattr(
        "kube_galaxy.pkg.components.strategies._base.download_file", fake_download_file
    )

    helm_repo_component.download_hook()

    assert len(download_calls) == 0
    assert helm_repo_component.chart_path is None


def test_download_fetches_chart_archive(helm_archive_component, monkeypatch, tmp_path):
    """When helm_repo=False, download_hook downloads the chart archive."""
    download_calls = []

    def fake_download_file(url, dest):
        download_calls.append((url, dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake-tgz")

    monkeypatch.setattr(
        "kube_galaxy.pkg.components.strategies._base.download_file", fake_download_file
    )

    helm_archive_component.download_hook()

    assert len(download_calls) == 1
    url, dest = download_calls[0]
    assert "chart-1.2.3.tgz" in url
    assert helm_archive_component.chart_path == dest
    assert dest.exists()


# --- bootstrap hook tests ---


def test_bootstrap_from_repo(helm_repo_component, monkeypatch):
    """When helm_repo=True, bootstrap adds repo and installs from it."""
    repo_add_calls = []
    install_repo_calls = []

    monkeypatch.setattr(
        "kube_galaxy.pkg.components.strategies.helm.helm_repo_add",
        lambda unit, name, url: repo_add_calls.append((name, url)),
    )
    monkeypatch.setattr(
        "kube_galaxy.pkg.components.strategies.helm.helm_install_from_repo",
        lambda unit, release, chart: install_repo_calls.append((release, chart)),
    )

    helm_repo_component.bootstrap_hook()

    assert repo_add_calls == [("projectcalico", "https://docs.tigera.io/calico/charts")]
    assert install_repo_calls == [("calico", "projectcalico/tigera-operator")]


def test_bootstrap_from_archive(helm_archive_component, monkeypatch, tmp_path):
    """When helm_repo=False and chart exists, bootstrap installs from archive."""
    install_archive_calls = []

    chart_path = tmp_path / "chart-1.2.3.tgz"
    chart_path.write_bytes(b"fake-tgz")
    helm_archive_component.chart_path = chart_path

    monkeypatch.setattr(
        "kube_galaxy.pkg.components.strategies.helm.helm_install_from_archive",
        lambda unit, release, path: install_archive_calls.append((release, path)),
    )

    helm_archive_component.bootstrap_hook()

    assert install_archive_calls == [("my-chart", chart_path)]


def test_bootstrap_raises_if_chart_missing(helm_archive_component):
    """When helm_repo=False and chart_path is None, bootstrap raises ComponentError."""
    with pytest.raises(ComponentError, match="chart not downloaded"):
        helm_archive_component.bootstrap_hook()


# --- verify hook tests ---


def test_verify_waits_for_workloads(helm_repo_component, monkeypatch):
    """Verify hook gets helm manifest and waits for workload rollout."""
    manifest_yaml = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: calico-controller
  namespace: kube-system
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: calico-node
  namespace: kube-system
---
apiVersion: v1
kind: Service
metadata:
  name: calico-svc
"""
    mock_unit = MockUnit()
    mock_unit.set_run_results(
        RunResult(0, manifest_yaml, ""),  # helm get manifest
        RunResult(0, "", ""),  # rollout status Deployment
        RunResult(0, "", ""),  # rollout status DaemonSet
    )
    helm_repo_component.unit = mock_unit  # type: ignore[assignment]

    helm_repo_component.verify_hook()

    # First call is helm get manifest
    helm_cmd = mock_unit.run_calls[0][0]
    assert "helm" in helm_cmd
    assert "get" in helm_cmd
    assert "manifest" in helm_cmd

    # Rollout status calls
    rollout_calls = [c for c, _ in mock_unit.run_calls if "rollout" in c and "status" in c]
    assert len(rollout_calls) == 2
    expected_deploy = [
        "kubectl", "rollout", "status", "deployment/calico-controller", "-n", "kube-system",
    ]
    expected_ds = [
        "kubectl", "rollout", "status", "daemonset/calico-node", "-n", "kube-system",
    ]
    assert expected_deploy in rollout_calls
    assert expected_ds in rollout_calls


def test_verify_raises_on_helm_failure(helm_repo_component, monkeypatch):
    """When helm get manifest fails, verify raises ComponentError."""
    mock_unit = MockUnit()

    # Make the helm call raise
    def exploding_run(cmd, **kwargs):
        raise ShellError(cmd, 1, "", "helm not found")

    mock_unit.run = exploding_run  # type: ignore[assignment]
    helm_repo_component.unit = mock_unit  # type: ignore[assignment]

    with pytest.raises(ComponentError, match="Failed to get helm manifest"):
        helm_repo_component.verify_hook()
