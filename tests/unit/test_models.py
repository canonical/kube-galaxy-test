"""Unit tests for manifest models."""

from kube_galaxy.pkg.manifest.models import ComponentConfig, Manifest, NetworkConfig, NodeConfig


def test_component_creation():
    """Test component config dataclass creation."""
    config = ComponentConfig(
        name="test-comp",
        category="test",
        release="1.0.0",
        repo="https://github.com/test/repo",
        format="Binary",
        use_spread=True,
    )
    assert config.name == "test-comp"
    assert config.use_spread is True
    assert config.format == "Binary"


def test_node_config_defaults():
    """Test node configuration defaults."""
    nodes = NodeConfig()
    assert nodes.control_plane == 1
    assert nodes.worker == 1


def test_node_config_custom():
    """Test node configuration with custom values."""
    nodes = NodeConfig(control_plane=3, worker=5)
    assert nodes.control_plane == 3
    assert nodes.worker == 5


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
    nodes = NodeConfig(control_plane=1, worker=2)
    components = [
        ComponentConfig(
            name="test",
            category="test",
            release="1.0.0",
            repo="https://github.com/test/repo",
            format="Binary",
        )
    ]
    networking = [
        NetworkConfig(name="default", service_cidr="10.96.0.0/12", pod_cidr="192.168.0.0/16")
    ]

    manifest = Manifest(
        name="test-cluster",
        description="Test cluster",
        kubernetes_version="1.35.0",
        nodes=nodes,
        components=components,
        networking=networking,
    )

    assert manifest.name == "test-cluster"
    assert manifest.kubernetes_version == "1.35.0"
    assert len(manifest.components) == 1
    assert len(manifest.networking) == 1


def test_manifest_get_component():
    """Test getting component config by name from manifest."""
    comp1 = ComponentConfig(
        name="comp1",
        category="test",
        release="1.0.0",
        repo="https://github.com/test/repo1",
        format="Binary",
    )
    comp2 = ComponentConfig(
        name="comp2",
        category="test",
        release="1.0.0",
        repo="https://github.com/test/repo2",
        format="Binary",
    )

    manifest = Manifest(
        name="test",
        description="test",
        kubernetes_version="1.35.0",
        nodes=NodeConfig(),
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
        nodes=NodeConfig(),
        networking=[net],
    )

    assert manifest.get_networking("default") == net
    assert manifest.get_networking() == net  # First by default
