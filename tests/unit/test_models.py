"""Unit tests for manifest models."""

from pathlib import Path

from kube_galaxy.pkg.literals import URLs
from kube_galaxy.pkg.manifest.models import (
    ArtifactConfig,
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    NetworkConfig,
    RegistryConfig,
    RepoInfo,
)
from kube_galaxy.pkg.manifest.models import (
    TestConfig as ComponentTestConfig,
)
from kube_galaxy.pkg.manifest.models import (
    TestMethod as ComponentTestMethod,
)


def test_component_creation():
    """Test component config dataclass creation."""
    installation = InstallConfig(
        method=InstallMethod.BINARY_ARCHIVE,
        source_format="https://example.com/{{ release }}/{{ arch }}/binary.tar.gz",
        bin_path="./*",
        repo=RepoInfo(base_url="https://github.com/test/repo"),
    )
    test = ComponentTestConfig(
        method=ComponentTestMethod.SPREAD,
        source_format="{{ repo.base-url }}/spread/kube-galaxy",
        repo=RepoInfo(base_url="https://github.com/test/repo"),
    )
    config = ComponentConfig(
        name="test-comp",
        category="test",
        release="1.0.0",
        installation=installation,
        test=test,
    )
    assert config.name == "test-comp"
    assert config.test is not None
    assert config.test.method == ComponentTestMethod.SPREAD
    assert config.installation.method == InstallMethod.BINARY_ARCHIVE


def test_component_no_test():
    """Test component config with no test config defaults to method=none."""
    installation = InstallConfig(
        method=InstallMethod.BINARY_ARCHIVE,
        source_format="https://example.com/binary.tar.gz",
        bin_path="./*",
    )
    config = ComponentConfig(
        name="test-comp",
        category="test",
        release="1.0.0",
        installation=installation,
    )
    assert config.test.method == ComponentTestMethod.NONE


def test_network_config_creation():
    """Test network configuration creation."""
    net = NetworkConfig(
        name="default",
        service_cidr="10.96.0.0/12",
        pod_cidr="192.168.0.0/16",
    )
    assert net.name == "default"
    assert net.service_cidr == "10.96.0.0/12"


def test_manifest_creation():
    """Test manifest dataclass creation."""
    installation = InstallConfig(
        method=InstallMethod.BINARY_ARCHIVE,
        source_format="https://example.com/{{ release }}/{{ arch }}/binary.tar.gz",
        bin_path="./*",
        repo=RepoInfo(base_url="https://github.com/test/repo"),
    )
    components = [
        ComponentConfig(
            name="test",
            category="test",
            release="1.0.0",
            installation=installation,
        )
    ]
    networking = [
        NetworkConfig(name="default", service_cidr="10.96.0.0/12", pod_cidr="192.168.0.0/16")
    ]

    manifest = Manifest(
        name="test-cluster",
        description="Test cluster",
        kubernetes_version="1.35.0",
        components=components,
        networking=networking,
    )

    assert manifest.name == "test-cluster"
    assert manifest.kubernetes_version == "1.35.0"
    assert len(manifest.components) == 1
    assert len(manifest.networking) == 1


def test_manifest_get_component():
    """Test getting component config by name from manifest."""
    installation = InstallConfig(
        method=InstallMethod.BINARY_ARCHIVE,
        source_format="https://example.com/{{ release }}/{{ arch }}/binary.tar.gz",
        bin_path="./*",
        repo=RepoInfo(base_url="https://github.com/test/repo1"),
    )
    comp1 = ComponentConfig(
        name="comp1",
        category="test",
        release="1.0.0",
        installation=installation,
    )
    comp2 = ComponentConfig(
        name="comp2",
        category="test",
        release="1.0.0",
        installation=InstallConfig(
            method=InstallMethod.BINARY_ARCHIVE,
            source_format="https://example.com/binary.tar.gz",
            bin_path="./*",
            repo=RepoInfo(base_url="https://github.com/test/repo2"),
        ),
    )

    manifest = Manifest(
        name="test",
        description="test",
        kubernetes_version="1.35.0",
        components=[comp1, comp2],
    )

    assert manifest.get_component("comp1") == comp1
    assert manifest.get_component("comp2") == comp2
    assert manifest.get_component("nonexistent") is None


def test_manifest_get_networking():
    """Test getting networking config from manifest."""
    net = NetworkConfig(name="default", service_cidr="10.96.0.0/12", pod_cidr="192.168.0.0/16")

    manifest = Manifest(
        name="test",
        description="test",
        kubernetes_version="1.35.0",
        networking=[net],
    )

    assert manifest.get_networking("default") == net
    assert manifest.get_networking() == net  # First by default


def test_registry_config_defaults():
    """Test RegistryConfig default values."""
    registry = RegistryConfig()
    assert registry.enabled is True
    assert registry.remote_registry == URLs.REGISTRY_K8S_IO
    assert registry.port == 5000


def test_registry_config_custom():
    """Test RegistryConfig with custom values."""
    registry = RegistryConfig(enabled=True, remote_registry="docker.io", port=6000)
    assert registry.enabled is True
    assert registry.remote_registry == "docker.io"
    assert registry.port == 6000


def test_artifact_config_defaults():
    """Test ArtifactConfig default values."""
    artifact = ArtifactConfig()
    assert isinstance(artifact.registry, RegistryConfig)
    assert artifact.registry.enabled is True


def test_manifest_has_artifact_field():
    """Test that Manifest includes an artifact field with defaults."""
    manifest = Manifest(name="m", description="", kubernetes_version="1.35.0")
    assert isinstance(manifest.artifact, ArtifactConfig)
    assert manifest.artifact.registry.enabled is True


def test_repo_info_remote():
    """Test RepoInfo for a remote repository."""
    repo = RepoInfo(base_url="https://github.com/org/repo")
    assert repo.base_url == "https://github.com/org/repo"


def test_repo_info_local_scheme():
    """Test that base_url with local:// scheme is stored as-is."""
    repo = RepoInfo(base_url="local://components/mycomp")
    assert repo.base_url == "local://components/mycomp"
    assert repo.subdir is None


def test_repo_info_gh_artifact_scheme():
    """Test that base_url with gh-artifact:// scheme is stored as-is."""
    repo = RepoInfo(base_url="gh-artifact://mycomp-artifact/spread/kube-galaxy/task.yaml")
    assert repo.base_url == "gh-artifact://mycomp-artifact/spread/kube-galaxy/task.yaml"


def test_repo_info_local_with_subdir():
    """Test RepoInfo local source with optional subdir."""
    repo = RepoInfo(base_url="local://components", subdir="sub")
    assert repo.base_url == "local://components"
    assert repo.subdir == "sub"


def test_repo_info_empty_base_url():
    """An empty base_url is stored as empty string."""
    repo = RepoInfo()
    assert repo.base_url == ""


def test_manifest_path_default():
    """Manifest.path defaults to empty Path."""
    m = Manifest(name="x", kubernetes_version="1.35.0")
    assert m.path == Path("")


def test_install_config_default_repo():
    """InstallConfig.repo defaults to empty RepoInfo."""
    install = InstallConfig(method=InstallMethod.NONE, source_format="", bin_path="")
    assert install.repo.base_url == ""


def test_test_config_default_repo():
    """TestConfig.repo defaults to empty RepoInfo."""
    test = ComponentTestConfig(method=ComponentTestMethod.SPREAD, source_format="")
    assert test.repo.base_url == ""
