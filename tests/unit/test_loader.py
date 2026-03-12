"""Unit tests for manifest loader."""

import pytest
import yaml

from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import TestMethod


def test_load_manifest(sample_manifest_file):
    """Test loading a manifest from file."""
    manifest = load_manifest(sample_manifest_file)

    assert manifest.name == "test-cluster"
    assert manifest.description == "Test cluster for unit tests"
    assert manifest.kubernetes_version == "1.35.0"


def test_load_manifest_components(sample_manifest_file):
    """Test loading components from manifest."""
    manifest = load_manifest(sample_manifest_file)

    assert len(manifest.components) == 2
    assert manifest.components[0].name == "containerd"
    assert manifest.components[0].test is None
    assert manifest.components[1].name == "coredns"
    assert manifest.components[1].test is not None
    assert manifest.components[1].test.method == TestMethod.SPREAD


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
    assert len(manifest.components) == 0
    assert len(manifest.networking) == 0


def test_load_manifest_test_local_repo(tmp_manifest_dir):
    """Test that test.repo with base-url: local sets is_local on TestConfig."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: local-test
kubernetes-version: "1.35.0"
components:
  - name: mycomp
    category: test
    release: "1.0.0"
    installation:
      method: none
    test:
      method: spread
      repo:
        base-url: local
      source-format: "{{ repo.base-url }}/components/{{ name }}"
"""
    )

    manifest = load_manifest(manifest_file)

    assert len(manifest.components) == 1
    comp = manifest.components[0]
    assert comp.test is not None
    assert comp.test.repo.is_local is True
    assert comp.test.repo.base_url == "local"
    assert comp.test.source_format == "{{ repo.base-url }}/components/{{ name }}"


def test_load_manifest_install_repo_explicit_base_url(tmp_manifest_dir):
    """Test that installation.repo with base-url: local sets is_local."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: local-test
kubernetes-version: "1.35.0"
components:
  - name: mycomp
    category: test
    release: "1.0.0"
    installation:
      method: none
      repo:
        base-url: local
"""
    )

    manifest = load_manifest(manifest_file)

    comp = manifest.components[0]
    assert comp.installation.repo.is_local is True
    assert comp.installation.repo.base_url == "local"


def test_load_manifest_invalid_repo(tmp_manifest_dir):
    """Test error when repo field in installation is invalid (missing base-url)."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: test
kubernetes-version: "1.35.0"
components:
  - name: bad
    category: test
    release: "1.0"
    installation:
      method: none
      repo:
        subdir: something
"""
    )

    with pytest.raises(ValueError, match="'repo' must be an object"):
        load_manifest(manifest_file)


def test_load_manifest_invalid_test_value(tmp_manifest_dir):
    """Test error when test field is an unexpected type (e.g. bare true)."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: test
kubernetes-version: "1.35.0"
components:
  - name: bad
    category: test
    release: "1.0"
    installation:
      method: none
    test: true
"""
    )

    with pytest.raises(ValueError, match="'test' must be an object"):
        load_manifest(manifest_file)


def test_load_manifest_remote_install_repo_not_local(sample_manifest_file):
    """Test that remote installation repos have is_local == False."""
    manifest = load_manifest(sample_manifest_file)

    for comp in manifest.components:
        assert comp.installation.repo.is_local is False
        assert comp.installation.repo.base_url not in ("", "local")
