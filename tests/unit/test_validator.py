"""Unit tests for manifest validator."""

from pathlib import Path

import pytest

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import (
    ArtifactConfig,
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    NodesConfig,
    ProviderConfig,
    RegistryConfig,
    RepoInfo,
)
from kube_galaxy.pkg.manifest.models import (
    TestConfig as ComponentTestConfig,
)
from kube_galaxy.pkg.manifest.models import (
    TestMethod as ComponentTestMethod,
)
from kube_galaxy.pkg.manifest.validator import (
    get_components_with_spread,
    validate_manifest,
)


def test_validate_manifest_valid(sample_manifest_file):
    """Test validating a valid manifest."""
    manifest = load_manifest(sample_manifest_file)
    # Should not raise
    validate_manifest(manifest)


def test_validate_manifest_no_name():
    """Test error when manifest has no name."""
    manifest = Manifest(
        name="",
        description="test",
        kubernetes_version="1.35.0",
    )

    with pytest.raises(ValueError, match="must have a 'name' field"):
        validate_manifest(manifest)


def test_validate_manifest_no_k8s_version():
    """Test error when manifest has no kubernetes version."""
    manifest = Manifest(
        name="test",
        description="test",
        kubernetes_version="",
    )

    with pytest.raises(ValueError, match="must have a 'kubernetes-version' field"):
        validate_manifest(manifest)


def test_get_components_with_spread(sample_manifest_file, tmp_path, monkeypatch):
    """Test getting components with spread enabled."""
    # Create test directory structure
    tests_root = tmp_path / "tests"
    coredns_test_path = tests_root / "coredns" / "spread" / "kube-galaxy"
    coredns_test_path.mkdir(parents=True, exist_ok=True)

    # Create task.yaml for coredns component
    task_yaml = coredns_test_path / "task.yaml"
    task_yaml.write_text("""
summary: Test coredns functionality
execute: |
    echo "Testing coredns"
""")

    # Monkeypatch SystemPaths.tests_root to return our temp directory
    monkeypatch.setattr(SystemPaths, "local_tests_root", lambda: tests_root)

    manifest = load_manifest(sample_manifest_file)
    spread_components = get_components_with_spread(manifest)

    assert len(spread_components) == 1
    assert spread_components[0].name == "coredns"
    assert spread_components[0].test.method == ComponentTestMethod.SPREAD


def test_tests_component_root_always_uses_tests_root(monkeypatch):
    """SystemPaths.tests_component_root always returns tests_root/<name>/spread/kube-galaxy/.

    This holds for both local and remote sources — by test time all task
    definitions must be installed under tests_root.
    """
    fake_root = Path("/fake/tests")
    monkeypatch.setattr(SystemPaths, "local_tests_root", lambda: fake_root)

    install = InstallConfig(
        method=InstallMethod.NONE, source_format="", bin_path="", retag_format=""
    )
    test = ComponentTestConfig(
        method=ComponentTestMethod.SPREAD,
        source_format="{{ repo.base-url }}/spread/kube-galaxy",
        repo=RepoInfo(base_url="https://github.com/org/repo"),
    )

    # Remote source
    remote_comp = ComponentConfig(
        name="mycomp",
        category="test",
        release="1.0.0",
        installation=install,
        test=test,
    )
    assert (
        SystemPaths.tests_component_root(remote_comp.name)
        == fake_root / "mycomp" / "spread/kube-galaxy/"
    )

    # Local source — same result
    local_test = ComponentTestConfig(
        method=ComponentTestMethod.SPREAD,
        source_format="{{ repo.base-url }}/components/mycomp",
        repo=RepoInfo(base_url="local://"),
    )
    local_comp = ComponentConfig(
        name="mycomp",
        category="test",
        release="1.0.0",
        installation=install,
        test=local_test,
    )
    assert (
        SystemPaths.tests_component_root(local_comp.name)
        == fake_root / "mycomp" / "spread/kube-galaxy/"
    )


def test_get_components_with_spread_local_source(tmp_path, monkeypatch):
    """Test get_components_with_spread finds a local component via tests_root.

    The download_file flow copies the local suite to tests_root;
    here we simulate that by pre-populating tests_root and patching the path.
    """
    tests_root = tmp_path / "tests"
    monkeypatch.setattr(SystemPaths, "local_tests_root", lambda: tests_root)

    # Simulate the copy that download_file would do
    task_dir = tests_root / "localcomp" / "spread" / "kube-galaxy"
    task_dir.mkdir(parents=True)
    (task_dir / "task.yaml").write_text("summary: local test\nexecute: |\n    echo done\n")

    install = InstallConfig(
        method=InstallMethod.NONE, source_format="", bin_path="", retag_format=""
    )
    test = ComponentTestConfig(
        method=ComponentTestMethod.SPREAD,
        source_format="{{ repo.base-url }}/components/{{ name }}",
        repo=RepoInfo(base_url="local://"),
    )
    comp = ComponentConfig(
        name="localcomp",
        category="test",
        release="1.0.0",
        installation=install,
        test=test,
    )
    manifest = Manifest(
        name="test",
        description="test",
        kubernetes_version="1.35.0",
        components=[comp],
    )

    spread_components = get_components_with_spread(manifest)
    assert len(spread_components) == 1
    assert spread_components[0].name == "localcomp"


def _minimal_manifest(**kwargs) -> Manifest:
    return Manifest(name="m", description="", kubernetes_version="1.35.0", **kwargs)


def test_validate_registry_port_zero_rejected():
    """Port 0 should be rejected when registry is enabled."""
    manifest = _minimal_manifest(
        artifact=ArtifactConfig(registry=RegistryConfig(enabled=True, port=0))
    )
    with pytest.raises(ValueError, match=r"artifact\.registry\.port"):
        validate_manifest(manifest)


def test_validate_registry_port_too_large_rejected():
    """Port 65536 should be rejected when registry is enabled."""
    manifest = _minimal_manifest(
        artifact=ArtifactConfig(registry=RegistryConfig(enabled=True, port=65536))
    )
    with pytest.raises(ValueError, match=r"artifact\.registry\.port"):
        validate_manifest(manifest)


def test_validate_registry_port_valid():
    """A valid port in range [1, 65535] should pass validation."""
    manifest = _minimal_manifest(
        artifact=ArtifactConfig(registry=RegistryConfig(enabled=True, port=5000))
    )
    validate_manifest(manifest)  # should not raise


def test_validate_registry_disabled_skips_port_check():
    """Port validation is skipped when registry.enabled is False."""
    manifest = _minimal_manifest(
        artifact=ArtifactConfig(registry=RegistryConfig(enabled=False, port=0))
    )
    validate_manifest(manifest)  # should not raise


def test_validate_provider_nodes_control_plane_zero_rejected():
    """provider.nodes.control-plane: 0 must be rejected."""
    manifest = _minimal_manifest(
        provider=ProviderConfig(nodes=NodesConfig(control_plane=0, worker=0))
    )
    with pytest.raises(ValueError, match=r"provider\.nodes\.control-plane"):
        validate_manifest(manifest)


def test_validate_provider_nodes_control_plane_negative_rejected():
    """Negative provider.nodes.control-plane must be rejected."""
    manifest = _minimal_manifest(
        provider=ProviderConfig(nodes=NodesConfig(control_plane=-1, worker=0))
    )
    with pytest.raises(ValueError, match=r"provider\.nodes\.control-plane"):
        validate_manifest(manifest)


def test_validate_provider_nodes_worker_negative_rejected():
    """Negative provider.nodes.worker must be rejected."""
    manifest = _minimal_manifest(
        provider=ProviderConfig(nodes=NodesConfig(control_plane=1, worker=-1))
    )
    with pytest.raises(ValueError, match=r"provider\.nodes\.worker"):
        validate_manifest(manifest)


def test_validate_provider_nodes_valid_passes():
    """Valid provider.nodes values should pass validation without error."""
    manifest = _minimal_manifest(
        provider=ProviderConfig(nodes=NodesConfig(control_plane=1, worker=0))
    )
    validate_manifest(manifest)  # should not raise
