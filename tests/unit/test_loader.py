"""Unit tests for manifest loader."""

import pytest
import yaml

from kube_galaxy.pkg.literals import URLs
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import TestMethod as ComponentTestMethod


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
    assert manifest.components[0].test.method == ComponentTestMethod.NONE
    assert manifest.components[1].name == "coredns"
    assert manifest.components[1].test.method == ComponentTestMethod.SPREAD


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


def test_load_manifest_artifact_absent_gives_defaults(tmp_manifest_dir):
    """Test that a manifest without an artifact block gets default ArtifactConfig."""
    manifest_file = tmp_manifest_dir / "no-artifact.yaml"
    manifest_file.write_text(
        """
name: minimal-cluster
kubernetes-version: "1.35.0"
"""
    )
    manifest = load_manifest(manifest_file)
    assert manifest.artifact.registry.enabled is True
    assert manifest.artifact.registry.remote_registry == URLs.REGISTRY_K8S_IO
    assert manifest.artifact.registry.port == 5000


def test_load_manifest_artifact_disabled_parses(tmp_manifest_dir):
    """Test that artifact.registry.enabled: false is parsed correctly."""
    manifest_file = tmp_manifest_dir / "artifact-disabled.yaml"
    manifest_file.write_text(
        """
name: minimal-cluster
kubernetes-version: "1.35.0"
artifact:
  registry:
    enabled: false
"""
    )
    manifest = load_manifest(manifest_file)
    assert manifest.artifact.registry.enabled is False


def test_load_manifest_artifact_fully_specified(tmp_manifest_dir):
    """Test loading artifact.registry with all fields explicitly set."""
    manifest_file = tmp_manifest_dir / "artifact-full.yaml"
    manifest_file.write_text(
        """
name: minimal-cluster
kubernetes-version: "1.35.0"
artifact:
  registry:
    enabled: true
    remote-registry: docker.io
    port: 6000
"""
    )
    manifest = load_manifest(manifest_file)
    assert manifest.artifact.registry.enabled is True
    assert manifest.artifact.registry.remote_registry == "docker.io"
    assert manifest.artifact.registry.port == 6000


def test_load_manifest_artifact_partial_override(tmp_manifest_dir):
    """Test that unset artifact fields fall back to defaults."""
    manifest_file = tmp_manifest_dir / "artifact-partial.yaml"
    manifest_file.write_text(
        """
name: minimal-cluster
kubernetes-version: "1.35.0"
artifact:
  registry:
    enabled: true
"""
    )
    manifest = load_manifest(manifest_file)
    assert manifest.artifact.registry.enabled is True
    assert manifest.artifact.registry.remote_registry == URLs.REGISTRY_K8S_IO
    assert manifest.artifact.registry.port == 5000


def test_load_manifest_test_local_repo(tmp_manifest_dir):
    """Test that test.repo with local:// base-url is loaded correctly."""
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
        base-url: local://components/mycomp
      source-format: "{{ repo.base-url }}/spread/kube-galaxy/task.yaml"
"""
    )

    manifest = load_manifest(manifest_file)

    assert len(manifest.components) == 1
    comp = manifest.components[0]
    assert comp.test.repo.base_url == "local://components/mycomp"
    assert comp.test.source_format == "{{ repo.base-url }}/spread/kube-galaxy/task.yaml"


def test_load_manifest_install_repo_explicit_base_url(tmp_manifest_dir):
    """Test that installation.repo with local:// base-url is loaded correctly."""
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
        base-url: local://components/mycomp
"""
    )

    manifest = load_manifest(manifest_file)

    comp = manifest.components[0]
    assert comp.installation.repo.base_url == "local://components/mycomp"


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

    with pytest.raises(AttributeError):
        load_manifest(manifest_file)


def test_load_manifest_remote_install_repo_not_local(sample_manifest_file):
    """Test that remote installation repos use https:// base-url."""
    manifest = load_manifest(sample_manifest_file)

    for comp in manifest.components:
        assert not comp.installation.repo.base_url.startswith("local://")
        assert comp.installation.repo.base_url != ""


def test_load_manifest_test_environment_loads_correctly(tmp_manifest_dir):
    """Test that test.environment key-value pairs are loaded correctly."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: env-test
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
        base-url: "https://github.com/org/repo"
      source-format: "{{ repo.base-url }}/spread/kube-galaxy"
      environment:
        SONOBUOY_MODE: quick
        KUBERNETES_VERSION: "1.35.0"
"""
    )

    manifest = load_manifest(manifest_file)

    comp = manifest.components[0]
    assert comp.test.environment == {
        "SONOBUOY_MODE": "quick",
        "KUBERNETES_VERSION": "1.35.0",
    }


def test_load_manifest_test_environment_defaults_to_empty_dict(tmp_manifest_dir):
    """Test that test.environment defaults to {} when absent from the manifest."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: env-test
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
        base-url: "https://github.com/org/repo"
      source-format: "{{ repo.base-url }}/spread/kube-galaxy"
"""
    )

    manifest = load_manifest(manifest_file)

    comp = manifest.components[0]
    assert comp.test.environment == {}


def test_load_manifest_test_environment_null_defaults_to_empty_dict(tmp_manifest_dir):
    """Test that test.environment: null is treated as an empty dict."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: env-test
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
        base-url: "https://github.com/org/repo"
      source-format: "{{ repo.base-url }}/spread/kube-galaxy"
      environment: null
"""
    )

    manifest = load_manifest(manifest_file)

    comp = manifest.components[0]
    assert comp.test.environment == {}


def test_load_manifest_test_environment_rejects_list(tmp_manifest_dir):
    """Test that test.environment rejects a list value with a clear ValueError."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: env-test
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
        base-url: "https://github.com/org/repo"
      source-format: "{{ repo.base-url }}/spread/kube-galaxy"
      environment:
        - INVALID_LIST_ITEM
"""
    )

    with pytest.raises(ValueError, match=r"'test\.environment' must be a mapping"):
        load_manifest(manifest_file)


def test_load_manifest_test_environment_rejects_non_string_value(tmp_manifest_dir):
    """Test that test.environment rejects non-string values with a clear ValueError."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: env-test
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
        base-url: "https://github.com/org/repo"
      source-format: "{{ repo.base-url }}/spread/kube-galaxy"
      environment:
        TIMEOUT: 30
"""
    )

    with pytest.raises(
        ValueError, match=r"'test\.environment' value for key 'TIMEOUT' must be a string"
    ):
        load_manifest(manifest_file)


def test_load_manifest_test_environment_rejects_non_string_key(tmp_manifest_dir):
    """Test that test.environment rejects non-string keys with a clear ValueError."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: env-test
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
        base-url: "https://github.com/org/repo"
      source-format: "{{ repo.base-url }}/spread/kube-galaxy"
      environment:
        123: "numeric-key"
"""
    )

    with pytest.raises(ValueError, match=r"'test\.environment' key must be a string"):
        load_manifest(manifest_file)


def test_load_manifest_test_environment_component_name_in_error(tmp_manifest_dir):
    """Test that ValueError messages include the component name for context."""
    manifest_file = tmp_manifest_dir / "test.yaml"
    manifest_file.write_text(
        """
name: env-test
kubernetes-version: "1.35.0"
components:
  - name: cncf-quick
    category: conformance
    release: "1.0.0"
    installation:
      method: none
    test:
      method: spread
      repo:
        base-url: "https://github.com/org/repo"
      source-format: "{{ repo.base-url }}/spread/kube-galaxy"
      environment: [bad, list]
"""
    )

    with pytest.raises(ValueError, match="Component cncf-quick"):
        load_manifest(manifest_file)


def test_load_manifest_provider_nodes_string_coerced_to_int(tmp_manifest_dir):
    """String node counts in provider.nodes are coerced to int."""
    manifest_file = tmp_manifest_dir / "provider-nodes.yaml"
    manifest_file.write_text(
        """
name: coerce-test
kubernetes-version: "1.35.0"
provider:
  nodes:
    control-plane: "2"
    worker: "3"
"""
    )
    manifest = load_manifest(manifest_file)
    assert manifest.provider.nodes.control_plane == 2
    assert isinstance(manifest.provider.nodes.control_plane, int)
    assert manifest.provider.nodes.worker == 3
    assert isinstance(manifest.provider.nodes.worker, int)
