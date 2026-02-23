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
    return ComponentConfig(
        name="calico",
        category="projectcalico/calico",
        release="3.30.6",
        repo="https://github.com/projectcalico/calico",
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
    config = ComponentConfig(
        name="test-component",
        category="test",
        release="v1.2.3",
        repo="myorg/myrepo",
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
    assert url == "https://example.com/myorg/myrepo/releases/v1.2.3/manifest-amd64.yaml"


def test_download_hook_adds_https_prefix(manifest, monkeypatch, tmp_path):
    """Test that download_hook adds https:// prefix when URL doesn't have protocol."""
    install = InstallConfig(
        method=InstallMethod.CONTAINER_MANIFEST,
        source_format="raw.githubusercontent.com/org/repo/v{release}/manifest.yaml",
    )
    config = ComponentConfig(
        name="test", category="test", release="1.0", repo="org/repo", installation=install
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


def test_delete_hook_deletes_manifest_resources(component, monkeypatch, tmp_path):
    """Test that delete_hook runs kubectl delete for CONTAINER_MANIFEST method."""
    # Setup: Create a manifest file
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("apiVersion: v1\nkind: ConfigMap\n")
    component.manifest_path = manifest_path

    run_calls = []

    def fake_run(cmd, **kwargs):
        run_calls.append((list(cmd), kwargs))

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # Call delete hook
    component.delete_hook()

    # Verify kubectl delete was called with check=False and timeout
    assert len(run_calls) == 1
    cmd, kwargs = run_calls[0]
    assert cmd == ["kubectl", "delete", "-f", str(manifest_path)]
    assert kwargs.get("check") is False
    assert "timeout" in kwargs


def test_delete_hook_handles_missing_manifest_gracefully(component, monkeypatch):
    """Test that delete_hook handles missing manifest file gracefully."""
    run_calls = []

    def fake_run(cmd, **kwargs):
        run_calls.append(cmd)

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # manifest_path is None, should not crash
    component.delete_hook()

    # No kubectl commands should be called
    assert len(run_calls) == 0


def test_delete_hook_handles_kubectl_errors_gracefully(component, monkeypatch, tmp_path):
    """Test that delete_hook continues even if kubectl delete fails."""
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("apiVersion: v1\nkind: ConfigMap\n")
    component.manifest_path = manifest_path

    def fake_run(cmd, **kwargs):
        raise RuntimeError("kubectl failed")

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # Should not raise an exception
    component.delete_hook()


def test_delete_hook_cleans_up_manifest_file(component, monkeypatch, tmp_path):
    """Test that delete_hook removes the manifest file after deleting resources."""
    manifest_path = Path(tmp_path) / "calico" / "temp" / "calico-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("apiVersion: v1\nkind: ConfigMap\n")
    component.manifest_path = manifest_path

    def fake_run(cmd, **kwargs):
        pass  # Simulate successful kubectl delete

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # Verify file exists before
    assert manifest_path.exists()

    component.delete_hook()

    # Verify file is removed after
    assert not manifest_path.exists()


def test_delete_hook_skips_non_manifest_components(manifest, monkeypatch):
    """Test that delete_hook doesn't affect components with other install methods."""
    install = InstallConfig(method=InstallMethod.BINARY, source_format="https://example/{arch}/bin")
    config = ComponentConfig(
        name="test-binary", category="test", release="v1", repo="org/repo", installation=install
    )

    comp = ComponentBase({}, manifest, config)

    run_calls = []

    def fake_run(cmd, **kwargs):
        run_calls.append(cmd)

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # Call delete hook - should do nothing for binary installs
    comp.delete_hook()

    # No kubectl commands should be called
    assert len(run_calls) == 0


def test_install_hook_does_nothing_for_manifest(component):
    """Test that install_hook does nothing for CONTAINER_MANIFEST method."""
    # install_hook should pass without error for container-manifest
    # It now just has a TODO and returns early
    component.install_hook()  # Should not raise an error


def test_verify_hook_has_todos(component):
    """Test that verify_hook exists and has TODO comments for future implementation."""
    # verify_hook should exist and not raise an error
    component.verify_hook()

    # Read the source to verify TODOs are present (this is a documentation check)
    import inspect

    source = inspect.getsource(ComponentBase.verify_hook)
    assert "TODO" in source
    assert "kubectl wait" in source or "manifest" in source.lower()

