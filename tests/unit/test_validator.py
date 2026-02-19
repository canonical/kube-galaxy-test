"""Unit tests for manifest validator."""

import pytest

from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import Manifest, NodeConfig
from kube_galaxy.pkg.manifest.validator import (
    get_component,
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
        nodes=NodeConfig(),
    )

    with pytest.raises(ValueError, match="must have a 'name' field"):
        validate_manifest(manifest)


def test_validate_manifest_no_k8s_version():
    """Test error when manifest has no kubernetes version."""
    manifest = Manifest(
        name="test",
        description="test",
        kubernetes_version="",
        nodes=NodeConfig(),
    )

    with pytest.raises(ValueError, match="must have a 'kubernetes-version' field"):
        validate_manifest(manifest)


def test_validate_manifest_no_control_plane():
    """Test error when manifest has no control plane nodes."""
    manifest = Manifest(
        name="test",
        description="test",
        kubernetes_version="1.35.0",
        nodes=NodeConfig(control_plane=0, worker=2),
    )

    with pytest.raises(ValueError, match="at least 1 control plane node"):
        validate_manifest(manifest)


def test_validate_manifest_negative_workers():
    """Test error when manifest has negative worker count."""
    manifest = Manifest(
        name="test",
        description="test",
        kubernetes_version="1.35.0",
        nodes=NodeConfig(control_plane=1, worker=-1),
    )

    with pytest.raises(ValueError, match="cannot be negative"):
        validate_manifest(manifest)


def test_get_components_with_spread(sample_manifest_file):
    """Test getting components with spread enabled."""
    manifest = load_manifest(sample_manifest_file)
    spread_components = get_components_with_spread(manifest)

    assert len(spread_components) == 1
    assert spread_components[0].name == "coredns"
    assert spread_components[0].use_spread is True


def test_get_component_by_name(sample_manifest_file):
    """Test getting component by name."""
    manifest = load_manifest(sample_manifest_file)
    component = get_component(manifest, "containerd")

    assert component is not None
    assert component.name == "containerd"
    assert component.use_spread is False


def test_get_component_not_found(sample_manifest_file):
    """Test getting nonexistent component."""
    manifest = load_manifest(sample_manifest_file)
    component = get_component(manifest, "nonexistent")

    assert component is None
