"""Unit tests for manifest validator."""

from pathlib import Path

import pytest

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    RepoInfo,
)
from kube_galaxy.pkg.manifest.validator import (
    get_components_with_spread,
    task_path_for_component,
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
    """Test getting components with spread enabled (remote repo)."""
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
    monkeypatch.setattr(SystemPaths, "tests_root", lambda: tests_root)

    manifest = load_manifest(sample_manifest_file)
    spread_components = get_components_with_spread(manifest)

    assert len(spread_components) == 1
    assert spread_components[0].name == "coredns"
    assert spread_components[0].test is True


def test_task_path_for_component_always_uses_tests_root(monkeypatch):
    """task_path_for_component always returns tests_root/<name>/spread/kube-galaxy/.

    This holds for both local and remote sources — by test time all task
    definitions must be installed under tests_root.
    """
    fake_root = Path("/fake/tests")
    monkeypatch.setattr(SystemPaths, "tests_root", lambda: fake_root)

    install = InstallConfig(method=InstallMethod.NONE, source_format="", bin_path="")

    # Remote source
    remote_comp = ComponentConfig(
        name="mycomp",
        category="test",
        release="1.0.0",
        repo=RepoInfo(base_url="https://github.com/org/repo"),
        installation=install,
        test=True,
    )
    assert task_path_for_component(remote_comp) == fake_root / "mycomp" / "spread/kube-galaxy/"

    # Local source — same result
    local_comp = ComponentConfig(
        name="mycomp",
        category="test",
        release="1.0.0",
        repo=RepoInfo(base_url="local"),
        installation=install,
        test=True,
    )
    assert task_path_for_component(local_comp) == fake_root / "mycomp" / "spread/kube-galaxy/"


def test_get_components_with_spread_local_source(tmp_path, monkeypatch):
    """Test get_components_with_spread finds a local component via tests_root.

    The download_tasks_from_config flow copies the local suite to tests_root;
    here we simulate that by pre-populating tests_root and patching the path.
    """
    tests_root = tmp_path / "tests"
    monkeypatch.setattr(SystemPaths, "tests_root", lambda: tests_root)

    # Simulate the copy that download_tasks_from_config would do
    task_dir = tests_root / "localcomp" / "spread" / "kube-galaxy"
    task_dir.mkdir(parents=True)
    (task_dir / "task.yaml").write_text("summary: local test\nexecute: |\n    echo done\n")

    install = InstallConfig(method=InstallMethod.NONE, source_format="", bin_path="")
    comp = ComponentConfig(
        name="localcomp",
        category="test",
        release="1.0.0",
        repo=RepoInfo(base_url="local"),
        installation=install,
        test=True,
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
