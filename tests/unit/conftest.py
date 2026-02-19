"""Shared pytest fixtures and configuration."""

import tempfile
from pathlib import Path

import pytest

# Ensure component modules are imported during tests so coverage includes them
import kube_galaxy.pkg.components  # noqa: F401


@pytest.fixture
def tmp_manifest_dir():
    """Temporary directory for test manifests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_manifest_yaml():
    """Sample manifest YAML content."""
    return """
name: test-cluster
description: Test cluster for unit tests
kubernetes-version: "1.35.0"
nodes:
  control-plane: 1
  worker: 2
components:
  - name: containerd
    category: containerd
    release: "2.1.0"
    repo: "https://github.com/containerd/containerd"
    format: "Binary"
    use-spread: false
  - name: coredns
    category: dns
    release: "1.10.1"
    repo: "https://github.com/coredns/coredns"
    format: "Binary"
    use-spread: true
networking:
  - name: default
    service-cidr: "10.96.0.0/12"
    pod-cidr: "192.168.0.0/16"
"""


@pytest.fixture
def sample_manifest_file(tmp_manifest_dir, sample_manifest_yaml):
    """Create a temporary manifest file."""
    manifest_file = tmp_manifest_dir / "test-manifest.yaml"
    manifest_file.write_text(sample_manifest_yaml)
    return manifest_file
