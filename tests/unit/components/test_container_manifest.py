"""Unit tests for container-manifest install method."""

from pathlib import Path

import pytest

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    RepoInfo,
)
from kube_galaxy.pkg.utils.errors import ComponentError


@pytest.fixture
def manifest():
    """Create a minimal manifest for testing."""
    return Manifest(name="test-cluster", description="Test", kubernetes_version="1.35.0")


@pytest.fixture
def calico_config():
    """Create a Calico component config with container-manifest method."""
    install = InstallConfig(
        method=InstallMethod.CONTAINER_MANIFEST,
        source_format="raw.githubusercontent.com/projectcalico/calico/v{release}/manifests/calico.yaml",
    )
    repo = RepoInfo(base_url="https://github.com/projectcalico/calico")
    return ComponentConfig(
        name="calico",
        category="projectcalico/calico",
        release="3.30.6",
        repo=repo,
        installation=install,
    )


@pytest.fixture
def component(manifest, calico_config, monkeypatch, tmp_path):
    """Create a ComponentBase instance with mocked temp directory."""
    # Redirect component temp dir to test tmp_path to avoid /opt writes
    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, name: Path(tmp_path) / name / "temp"),
    )
    return ComponentBase({}, manifest, calico_config)


def test_download_hook_downloads_manifest(component, monkeypatch, tmp_path):
    """Test that download_hook downloads manifest file for CONTAINER_MANIFEST method."""
    download_calls = []

    def fake_download_file(url: str, dest: Path):
        download_calls.append((url, dest))
        # Create the file so it exists
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("apiVersion: v1\nkind: ConfigMap\n")

    monkeypatch.setattr("kube_galaxy.pkg.components._base.download_file", fake_download_file)

    # Call download hook
    component.download_hook()

    # Verify download was called with proper URL (https:// prefix added)
    assert len(download_calls) == 1
    url, dest = download_calls[0]
    assert (
        url
        == "https://raw.githubusercontent.com/projectcalico/calico/v3.30.6/manifests/calico.yaml"
    )
    assert dest.name == "calico-manifest.yaml"
    assert component.manifest_path == dest
    assert component.manifest_path.exists()


def test_download_hook_formats_url_with_placeholders(manifest, monkeypatch, tmp_path):
    """Test that download_hook properly formats URLs with release, repo, and arch placeholders."""
    install = InstallConfig(
        method=InstallMethod.CONTAINER_MANIFEST,
        source_format="https://example.com/{repo}/releases/{release}/manifest-{arch}.yaml",
    )
    repo = RepoInfo(base_url="https://github.com/myorg/myrepo")
    config = ComponentConfig(
        name="test-component",
        category="test",
        release="v1.2.3",
        repo=repo,
        installation=install,
    )

    # Redirect component temp dir
    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, name: Path(tmp_path) / name / "temp"),
    )
    comp = ComponentBase({}, manifest, config)

    download_calls = []

    def fake_download_file(url: str, dest: Path):
        download_calls.append((url, dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("manifest content")

    monkeypatch.setattr("kube_galaxy.pkg.components._base.download_file", fake_download_file)

    comp.download_hook()

    # Verify URL formatting
    url, _ = download_calls[0]
    # Determine expected architecture from the component, falling back to "amd64" if unavailable
    arch_info = getattr(comp, "arch_info", None)
    arch = getattr(arch_info, "arch", "amd64") if arch_info is not None else "amd64"
    expected_url = (
        f"https://example.com/https://github.com/myorg/myrepo/releases/v1.2.3/manifest-{arch}.yaml"
    )
    assert url == expected_url


def test_download_hook_adds_https_prefix(manifest, monkeypatch, tmp_path):
    """Test that download_hook adds https:// prefix when URL doesn't have protocol."""
    install = InstallConfig(
        method=InstallMethod.CONTAINER_MANIFEST,
        source_format="raw.githubusercontent.com/org/repo/v{release}/manifest.yaml",
    )
    repo = RepoInfo(base_url="https://github.com/myorg/myrepo")
    config = ComponentConfig(
        name="test", category="test", release="1.0", repo=repo, installation=install
    )

    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, name: Path(tmp_path) / name / "temp"),
    )
    comp = ComponentBase({}, manifest, config)

    download_calls = []

    def fake_download_file(url: str, dest: Path):
        download_calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("content")

    monkeypatch.setattr("kube_galaxy.pkg.components._base.download_file", fake_download_file)

    comp.download_hook()

    # Verify https:// was added
    assert download_calls[0].startswith("https://")


def test_bootstrap_hook_applies_manifest(component, monkeypatch, tmp_path):
    """Test that bootstrap_hook runs kubectl apply for CONTAINER_MANIFEST method."""
    # Setup: Create a downloaded manifest
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("apiVersion: v1\nkind: ConfigMap\n")
    component.manifest_path = manifest_path

    run_calls = []

    def fake_run(cmd, **kwargs):
        run_calls.append((list(cmd), kwargs))

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # Call bootstrap hook
    component.bootstrap_hook()

    # Verify kubectl apply was called
    assert len(run_calls) == 1
    cmd, kwargs = run_calls[0]
    assert cmd == ["kubectl", "apply", "-f", str(manifest_path)]
    assert kwargs.get("check") is True


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


def test_delete_hook_does_nothing_in_base_class(component, monkeypatch, tmp_path):
    """Test that delete_hook base implementation does nothing for CONTAINER_MANIFEST method."""
    # Setup: Create a manifest file
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("apiVersion: v1\nkind: ConfigMap\n")
    component.manifest_path = manifest_path

    run_calls = []

    def fake_run(cmd, **kwargs):
        run_calls.append((list(cmd), kwargs))

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # Call delete hook - base class should do nothing
    component.delete_hook()

    # No kubectl commands should be called in base class
    assert len(run_calls) == 0


def test_delete_hook_handles_missing_manifest_gracefully(component):
    """Test that delete_hook handles missing manifest file gracefully."""
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
    component.delete_hook()


def test_delete_hook_preserves_manifest_file(component, tmp_path):
    """Test that base delete_hook does not remove the manifest file."""
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("apiVersion: v1\nkind: ConfigMap\n")
    component.manifest_path = manifest_path

    # Verify file exists before
    assert manifest_path.exists()

    component.delete_hook()

    # Verify file still exists after (base class does nothing)
    assert manifest_path.exists()


def test_delete_hook_works_for_all_install_methods(manifest):
    """Test that delete_hook base implementation works for all install methods."""
    install = InstallConfig(method=InstallMethod.BINARY, source_format="https://example/{arch}/bin")
    repo = RepoInfo(base_url="https://github.com/org/repo")
    config = ComponentConfig(
        name="test-binary", category="test", release="v1", repo=repo, installation=install
    )

    comp = ComponentBase({}, manifest, config)

    # Call delete hook - should do nothing for any install method in base class
    comp.delete_hook()
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

    run_calls = []

    # Mock kubectl create --dry-run to return parsed YAML
    def fake_run(cmd, **kwargs):
        if "create" in cmd and "--dry-run=client" in cmd:
            # Return the manifest content as stdout
            class FakeResult:
                stdout = manifest_content

            run_calls.append(("create-dry-run", list(cmd), kwargs))
            return FakeResult()
        elif "rollout" in cmd and "status" in cmd:
            run_calls.append(("rollout-status", list(cmd), kwargs))
            return None
        return None

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # Call verify hook
    component.verify_hook()

    # Verify kubectl create --dry-run was called
    create_calls = [c for c in run_calls if c[0] == "create-dry-run"]
    assert len(create_calls) == 1
    _, cmd, kwargs = create_calls[0]
    assert "kubectl" in cmd
    assert "--dry-run=client" in cmd
    assert "-f" in cmd
    assert str(manifest_path) in cmd
    assert kwargs.get("check") is True
    assert kwargs.get("capture_output") is True

    # Verify kubectl rollout status was called for each workload
    rollout_calls = [c for c in run_calls if c[0] == "rollout-status"]
    assert len(rollout_calls) == 2  # Deployment and DaemonSet

    # Check deployment rollout
    deployment_calls = [c for c in rollout_calls if "deployment" in " ".join(c[1])]
    assert len(deployment_calls) == 1
    _, cmd, kwargs = deployment_calls[0]
    assert cmd == [
        "kubectl",
        "rollout",
        "status",
        "deployment/calico-kube-controllers",
        "-n",
        "kube-system",
    ]
    assert kwargs.get("check") is True
    assert "timeout" in kwargs

    # Check daemonset rollout
    daemonset_calls = [c for c in rollout_calls if "daemonset" in " ".join(c[1])]
    assert len(daemonset_calls) == 1
    _, cmd, kwargs = daemonset_calls[0]
    assert cmd == ["kubectl", "rollout", "status", "daemonset/calico-node", "-n", "kube-system"]
    assert kwargs.get("check") is True
    assert "timeout" in kwargs


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

    run_calls = []

    def fake_run(cmd, **kwargs):
        if "create" in cmd and "--dry-run=client" in cmd:

            class FakeResult:
                stdout = manifest_content

            return FakeResult()
        elif "rollout" in cmd:
            run_calls.append(list(cmd))

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    component.verify_hook()

    # Verify default namespace was used
    assert len(run_calls) == 1
    assert run_calls[0] == [
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

    run_calls = []

    def fake_run(cmd, **kwargs):
        if "create" in cmd and "--dry-run=client" in cmd:

            class FakeResult:
                stdout = manifest_content

            return FakeResult()
        elif "rollout" in cmd:
            run_calls.append(list(cmd))

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    component.verify_hook()

    # No rollout status calls should be made for non-workload resources
    assert len(run_calls) == 0


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

    run_calls = []

    def fake_run(cmd, **kwargs):
        if "create" in cmd and "--dry-run=client" in cmd:

            class FakeResult:
                stdout = manifest_content

            return FakeResult()
        elif "rollout" in cmd:
            run_calls.append(list(cmd))

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    component.verify_hook()

    # Verify statefulset rollout was called
    assert len(run_calls) == 1
    assert run_calls[0] == [
        "kubectl",
        "rollout",
        "status",
        "statefulset/my-statefulset",
        "-n",
        "test-ns",
    ]
