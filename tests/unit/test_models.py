"""Unit tests for manifest models."""

from pathlib import Path

from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    NetworkConfig,
    RepoInfo,
)


def test_component_creation():
    """Test component config dataclass creation."""
    installation = InstallConfig(
        method=InstallMethod.BINARY_ARCHIVE,
        source_format="https://example.com/{release}/{arch}/binary.tar.gz",
        bin_path="./*",
    )
    config = ComponentConfig(
        name="test-comp",
        category="test",
        release="1.0.0",
        repo=RepoInfo(base_url="https://github.com/test/repo"),
        installation=installation,
        test=True,
    )
    assert config.name == "test-comp"
    assert config.test is True
    assert config.installation.method == InstallMethod.BINARY_ARCHIVE


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
        source_format="https://example.com/{release}/{arch}/binary.tar.gz",
        bin_path="./*",
    )
    components = [
        ComponentConfig(
            name="test",
            category="test",
            release="1.0.0",
            repo=RepoInfo(base_url="https://github.com/test/repo"),
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
        source_format="https://example.com/{release}/{arch}/binary.tar.gz",
        bin_path="./*",
    )
    comp1 = ComponentConfig(
        name="comp1",
        category="test",
        release="1.0.0",
        repo=RepoInfo(base_url="https://github.com/test/repo1"),
        installation=installation,
    )
    comp2 = ComponentConfig(
        name="comp2",
        category="test",
        release="1.0.0",
        repo=RepoInfo(base_url="https://github.com/test/repo2"),
        installation=installation,
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


def test_repo_info_remote():
    """Test RepoInfo for a remote repository."""
    repo = RepoInfo(base_url="https://github.com/org/repo")
    assert repo.base_url == "https://github.com/org/repo"
    assert repo.local is None
    assert repo.is_local is False


def test_repo_info_local_path():
    """Test RepoInfo for a local filesystem source."""
    local_path = Path("/some/local/path")
    repo = RepoInfo(local=local_path)
    assert repo.local == local_path
    assert repo.base_url == ""
    assert repo.is_local is True


def test_repo_info_local_with_subdir():
    """Test RepoInfo local source with subdir."""
    local_path = Path("/project/components/mycomp")
    repo = RepoInfo(local=local_path, subdir="sub")
    assert repo.is_local is True
    assert repo.subdir == "sub"
