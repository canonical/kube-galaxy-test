"""Unit tests for manifest loader."""

import pytest
import yaml

from kube_galaxy.pkg.manifest.loader import load_manifest


def test_load_manifest(sample_manifest_file):
    """Test loading a manifest from file."""
    manifest = load_manifest(sample_manifest_file)

    assert manifest.name == "test-cluster"
    assert manifest.description == "Test cluster for unit tests"
    assert manifest.kubernetes_version == "1.35.0"
    assert manifest.nodes.control_plane == 1
    assert manifest.nodes.worker == 2


def test_load_manifest_components(sample_manifest_file):
    """Test loading components from manifest."""
    manifest = load_manifest(sample_manifest_file)

    assert len(manifest.components) == 2
    assert manifest.components[0].name == "containerd"
    assert manifest.components[0].use_spread is False
    assert manifest.components[1].name == "coredns"
    assert manifest.components[1].use_spread is True


def test_load_manifest_networking(sample_manifest_file):
    """Test loading networking from manifest."""
    manifest = load_manifest(sample_manifest_file)

    assert len(manifest.networking) == 1
    assert manifest.networking[0].name == "default"
    assert manifest.networking[0].service_cidr == "10.96.0.0/12"
    assert manifest.networking[0].pod_cidr == "192.168.0.0/16"


def test_load_manifest_file_not_found():
    """Test error when manifest file not found."""
    with pytest.raises(FileNotFoundError):
        load_manifest("/nonexistent/path/manifest.yaml")


def test_load_manifest_invalid_yaml(tmp_manifest_dir):
    """Test error when manifest YAML is invalid."""
    manifest_file = tmp_manifest_dir / "invalid.yaml"
    manifest_file.write_text("invalid: yaml: content: [")

    with pytest.raises(yaml.YAMLError):
        load_manifest(manifest_file)


def test_load_manifest_not_dict(tmp_manifest_dir):
    """Test error when manifest is not a dictionary."""
    manifest_file = tmp_manifest_dir / "not-dict.yaml"
    manifest_file.write_text("- item1\n- item2\n")

    with pytest.raises(ValueError, match="must be a YAML dictionary"):
        load_manifest(manifest_file)


def test_load_manifest_defaults(tmp_manifest_dir):
    """Test manifest loading with defaults."""
    manifest_file = tmp_manifest_dir / "minimal.yaml"
    manifest_file.write_text(
        """
name: minimal-cluster
kubernetes-version: "1.35.0"
"""
    )

    manifest = load_manifest(manifest_file)

    assert manifest.name == "minimal-cluster"
    assert manifest.description == ""
    assert manifest.nodes.control_plane == 1
    assert manifest.nodes.worker == 1
    assert len(manifest.components) == 0
    assert len(manifest.networking) == 0
