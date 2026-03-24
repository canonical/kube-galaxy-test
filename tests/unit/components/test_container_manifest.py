"""Unit tests for container-manifest install method."""

from pathlib import Path

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
from tests.unit.components.conftest import MockUnit


@pytest.fixture
def manifest():
    """Create a minimal manifest for testing."""
    return Manifest(name="test-cluster", description="Test", kubernetes_version="1.35.0")


@pytest.fixture
def calico_config():
    """Create a Calico component config with container-manifest method."""
    repo = RepoInfo(base_url="https://github.com/projectcalico/calico")
    install = InstallConfig(
        method=InstallMethod.CONTAINER_MANIFEST,
        source_format=(
            "https://raw.githubusercontent.com/projectcalico/"
            "calico/v{{ release }}/manifests/calico.yaml"
        ),
        bin_path="./*",
        repo=repo,
    )
    return ComponentConfig(
        name="calico",
        category="projectcalico/calico",
        release="3.30.6",
        installation=install,
    )


@pytest.fixture
def component(
    manifest,
    arch_info,
    calico_config,
    monkeypatch,
    tmp_path,
):
    """Create a ComponentBase instance with mocked temp directory."""
    # Redirect staging root to test tmp_path to avoid cwd writes
    monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))
    return ComponentBase(ClusterContext(), manifest, calico_config, arch_info)


def test_download_hook_downloads_manifest(component, monkeypatch, tmp_path):
    """Test that download_hook downloads manifest file for CONTAINER_MANIFEST method."""
    download_calls = []

    def fake_download_file(url: str, dest: Path):
        download_calls.append((url, dest))
        # Create the file so it exists
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("apiVersion: v1\nkind: ConfigMap\n")

    _target = "kube_galaxy.pkg.components.strategies._base.download_file"
    monkeypatch.setattr(_target, fake_download_file)

    # Call download hook
    component.download_hook()

    # Verify download was called with proper URL (https:// prefix added)
    assert len(download_calls) == 1
    url, dest = download_calls[0]
    assert (
        url
        == "https://raw.githubusercontent.com/projectcalico/calico/v3.30.6/manifests/calico.yaml"
    )
    assert dest.name == "calico.yaml"
    assert component.manifest_path == dest
    assert component.manifest_path.exists()


def test_download_hook_formats_url_with_placeholders(manifest, arch_info, monkeypatch, tmp_path):
    """Test that download_hook properly formats URLs with release, repo, and arch placeholders."""
    repo = RepoInfo(base_url="https://github.com/myorg/myrepo")
    install = InstallConfig(
        method=InstallMethod.CONTAINER_MANIFEST,
        source_format="{{ repo.base-url }}/releases/{{ release }}/manifest-{{ arch }}.yaml",
        bin_path="./*",
        repo=repo,
    )
    config = ComponentConfig(
        name="test-component",
        category="test",
        release="v1.2.3",
        installation=install,
    )

    # Redirect component temp dir
    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, name: Path(tmp_path) / name / "temp"),
    )
    comp = ComponentBase(ClusterContext(), manifest, config, arch_info)

    download_calls = []

    def fake_download_file(url: str, dest: Path):
        download_calls.append((url, dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("manifest content")

    _target = "kube_galaxy.pkg.components.strategies._base.download_file"
    monkeypatch.setattr(_target, fake_download_file)

    comp.download_hook()

    # Verify URL formatting
    url, _ = download_calls[0]
    # Determine expected architecture from the component, falling back to "amd64" if unavailable
    arch_info = getattr(comp, "arch_info", None)
    arch = getattr(arch_info, "k8s", "amd64") if arch_info is not None else "amd64"
    expected_url = f"https://github.com/myorg/myrepo/releases/v1.2.3/manifest-{arch}.yaml"
    assert url == expected_url


def test_bootstrap_hook_applies_manifest(component, monkeypatch, tmp_path):
    """Test that bootstrap_hook runs kubectl apply for CONTAINER_MANIFEST method."""
    # Setup: Create a downloaded manifest
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("apiVersion: v1\nkind: ConfigMap\n")
    component.manifest_path = manifest_path

    apply_manifest_calls = []

    def fake_apply_manifest(unit, path):
        apply_manifest_calls.append(path)

    _target = "kube_galaxy.pkg.components.strategies.container_manifest.apply_manifest"
    monkeypatch.setattr(_target, fake_apply_manifest)

    # Call bootstrap hook
    component.bootstrap_hook()

    # Verify apply_manifest was called with the correct path
    assert len(apply_manifest_calls) == 1
    assert apply_manifest_calls[0] == manifest_path


def test_bootstrap_hook_fails_if_manifest_not_downloaded(component):
    """Test that bootstrap_hook raises error if manifest not downloaded."""
    # manifest_path is None by default
    with pytest.raises(ComponentError, match="manifest not downloaded"):
        component.bootstrap_hook()


def test_bootstrap_hook_fails_if_manifest_file_missing(component, tmp_path):
    """Test that bootstrap_hook raises error if manifest file doesn't exist."""
    # Set manifest_path but don't create the file
    component.manifest_path = Path(tmp_path) / "nonexistent.yaml"

    with pytest.raises(ComponentError, match="manifest not downloaded"):
        component.bootstrap_hook()


def test_delete_hook_does_nothing_in_base_class(component, tmp_path):
    """Test that delete_hook base implementation does not call kubectl for CONTAINER_MANIFEST."""

    # Inject mock unit to capture commands (no kubectl should be called)
    mock_unit = MockUnit()
    component.unit = mock_unit  # type: ignore[assignment]

    # Setup: Create a manifest file
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("apiVersion: v1\nkind: ConfigMap\n")
    component.manifest_path = manifest_path

    # Call delete hook - base class should not call kubectl
    component.delete_hook()

    # No kubectl commands should be called in base class
    kubectl_calls = [c for c, _ in mock_unit.run_calls if "kubectl" in c]
    assert len(kubectl_calls) == 0


def test_delete_hook_handles_missing_manifest_gracefully(component):
    """Test that delete_hook handles missing manifest file gracefully."""
    component.unit = MockUnit()
    # manifest_path is None, should not crash
    component.delete_hook()
    # Base implementation does nothing, so this should just pass


def test_delete_hook_base_implementation_does_nothing(component, tmp_path):
    """Test that base delete_hook implementation does nothing."""
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("apiVersion: v1\nkind: ConfigMap\n")
    component.manifest_path = manifest_path

    # Should not raise an exception and should do nothing
    component.unit = MockUnit()
    component.delete_hook()


def test_delete_hook_preserves_manifest_file(component, tmp_path):
    """Test that base delete_hook does not remove the manifest file."""
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("apiVersion: v1\nkind: ConfigMap\n")
    component.manifest_path = manifest_path

    # Verify file exists before
    assert manifest_path.exists()

    component.unit = MockUnit()
    component.delete_hook()

    # Verify file still exists after (base class does nothing)
    assert manifest_path.exists()


def test_delete_hook_works_for_all_install_methods(manifest, arch_info):
    """Test that delete_hook base implementation works for all install methods."""
    repo = RepoInfo(base_url="https://github.com/org/repo")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="https://example/{{ arch }}/bin",
        bin_path="./*",
        repo=repo,
    )
    config = ComponentConfig(
        name="test-binary", category="test", release="v1", installation=install
    )

    component = ComponentBase(ClusterContext(), manifest, config, arch_info)

    # Call delete hook - should do nothing for any install method in base class
    component.unit = MockUnit()
    component.delete_hook()
    # Base implementation does nothing, so this should just pass


def test_install_hook_does_nothing_for_manifest(component):
    """Test that install_hook does nothing for CONTAINER_MANIFEST method."""
    # install_hook should pass without error for container-manifest
    # It now just has a TODO and returns early
    component.install_hook()  # Should not raise an error


def test_verify_hook_parses_manifest_and_waits_for_workloads(component, monkeypatch, tmp_path):
    """Test that verify_hook parses manifest and waits for workload rollout status."""

    # Setup: Create a manifest file
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_content = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: calico-kube-controllers
  namespace: kube-system
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: calico-node
  namespace: kube-system
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: calico-config
"""
    manifest_path.write_text(manifest_content)
    component.manifest_path = manifest_path

    # Mock unit: first run() call (dry-run) returns manifest_content
    mock_unit = MockUnit()
    mock_unit.set_run_results(
        RunResult(0, manifest_content, ""),  # dry-run result
        RunResult(0, "", ""),  # rollout status for Deployment
        RunResult(0, "", ""),  # rollout status for DaemonSet
    )
    component.unit = mock_unit  # type: ignore[assignment]

    # Call verify hook
    component.verify_hook()

    # Verify kubectl create --dry-run was called
    dry_run_calls = [c for c, _ in mock_unit.run_calls if "--dry-run=client" in c]
    assert len(dry_run_calls) == 1
    cmd = dry_run_calls[0]
    assert "kubectl" in cmd
    assert "-f" in cmd
    # source puts the file via unit.put() then references the remote temp path
    assert any(str(manifest_path) in str(local) for local, _ in mock_unit.put_calls)

    # Verify kubectl rollout status was called for each workload
    rollout_calls = [c for c, _ in mock_unit.run_calls if "rollout" in c and "status" in c]
    assert len(rollout_calls) == 2

    # Check deployment rollout
    deployment_calls = [c for c in rollout_calls if "deployment" in " ".join(c)]
    assert len(deployment_calls) == 1
    assert deployment_calls[0] == [
        "kubectl",
        "rollout",
        "status",
        "deployment/calico-kube-controllers",
        "-n",
        "kube-system",
    ]

    # Check daemonset rollout
    daemonset_calls = [c for c in rollout_calls if "daemonset" in " ".join(c)]
    assert len(daemonset_calls) == 1
    assert daemonset_calls[0] == [
        "kubectl",
        "rollout",
        "status",
        "daemonset/calico-node",
        "-n",
        "kube-system",
    ]


def test_verify_hook_handles_default_namespace(component, monkeypatch, tmp_path):
    """Test that verify_hook uses 'default' namespace when not specified in manifest."""

    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_content = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
"""
    manifest_path.write_text(manifest_content)
    component.manifest_path = manifest_path

    mock_unit = MockUnit()
    mock_unit.set_run_results(
        RunResult(0, manifest_content, ""),
        RunResult(0, "", ""),
    )
    component.unit = mock_unit  # type: ignore[assignment]

    component.verify_hook()

    rollout_calls = [c for c, _ in mock_unit.run_calls if "rollout" in c and "status" in c]
    assert len(rollout_calls) == 1
    assert rollout_calls[0] == [
        "kubectl",
        "rollout",
        "status",
        "deployment/my-deployment",
        "-n",
        "default",
    ]


def test_verify_hook_skips_non_workload_resources(component, monkeypatch, tmp_path):
    """Test that verify_hook only waits for Deployment, DaemonSet, and StatefulSet."""

    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_content = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
---
apiVersion: v1
kind: Service
metadata:
  name: my-service
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: my-role
"""
    manifest_path.write_text(manifest_content)
    component.manifest_path = manifest_path

    mock_unit = MockUnit()
    mock_unit.set_run_results(RunResult(0, manifest_content, ""))
    component.unit = mock_unit  # type: ignore[assignment]

    component.verify_hook()

    # No rollout status calls should be made for non-workload resources
    rollout_calls = [c for c, _ in mock_unit.run_calls if "rollout" in c]
    assert len(rollout_calls) == 0


def test_verify_hook_fails_if_manifest_not_downloaded(component):
    """Test that verify_hook raises error if manifest not downloaded."""
    # manifest_path is None by default
    with pytest.raises(ComponentError, match="manifest not downloaded"):
        component.verify_hook()


def test_verify_hook_fails_if_manifest_file_missing(component, tmp_path):
    """Test that verify_hook raises error if manifest file doesn't exist."""
    component.manifest_path = Path(tmp_path) / "nonexistent.yaml"

    with pytest.raises(ComponentError, match="manifest not downloaded"):
        component.verify_hook()


def test_verify_hook_handles_statefulset(component, monkeypatch, tmp_path):
    """Test that verify_hook properly handles StatefulSet workloads."""

    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_content = """
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: my-statefulset
  namespace: test-ns
"""
    manifest_path.write_text(manifest_content)
    component.manifest_path = manifest_path

    mock_unit = MockUnit()
    mock_unit.set_run_results(
        RunResult(0, manifest_content, ""),
        RunResult(0, "", ""),
    )
    component.unit = mock_unit  # type: ignore[assignment]

    component.verify_hook()

    # Verify statefulset rollout was called
    rollout_calls = [c for c, _ in mock_unit.run_calls if "rollout" in c and "status" in c]
    assert len(rollout_calls) == 1
    assert rollout_calls[0] == [
        "kubectl",
        "rollout",
        "status",
        "statefulset/my-statefulset",
        "-n",
        "test-ns",
    ]
