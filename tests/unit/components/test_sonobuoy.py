"""Unit tests for the Sonobuoy component."""

from kube_galaxy.pkg.components import COMPONENTS
from kube_galaxy.pkg.components.sonobuoy import Sonobuoy
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    RepoInfo,
)


def make_sonobuoy_config() -> ComponentConfig:
    """Create a minimal sonobuoy component config with local source."""
    install = InstallConfig(method=InstallMethod.NONE, source_format="", bin_path="./*")
    repo = RepoInfo(base_url="local")
    return ComponentConfig(
        name="sonobuoy",
        category="vmware-tanzu/sonobuoy",
        release="0.57.3",
        repo=repo,
        installation=install,
        test=True,
    )


def test_sonobuoy_is_registered():
    """Sonobuoy class is registered in the COMPONENTS registry."""
    assert "sonobuoy" in COMPONENTS
    assert COMPONENTS["sonobuoy"] is Sonobuoy


def test_sonobuoy_is_local():
    """Sonobuoy config's repo.is_local should be True."""
    cfg = make_sonobuoy_config()
    assert cfg.repo.is_local is True


def test_sonobuoy_install_hook_copies_suite(tmp_path, monkeypatch, arch_info):
    """install_hook copies cwd/components/sonobuoy to tests_root/sonobuoy."""
    # Set cwd to a temp dir so local source path is controlled
    monkeypatch.chdir(tmp_path)

    # Create a fake local suite under cwd/components/sonobuoy/
    local_suite = tmp_path / "components" / "sonobuoy" / "spread" / "kube-galaxy"
    local_suite.mkdir(parents=True)
    (local_suite / "task.yaml").write_text("summary: test\nexecute: |\n  echo hi\n")

    # Redirect tests_root to a temp location
    tests_root = tmp_path / "tests"
    tests_root.mkdir()
    monkeypatch.setattr(SystemPaths, "tests_root", lambda: tests_root)

    cfg = make_sonobuoy_config()
    manifest = Manifest(name="m", description="d", kubernetes_version="1.35.0")
    comp = Sonobuoy({}, manifest, cfg, arch_info)

    comp.install_hook()

    # The task.yaml should now live under tests_root/sonobuoy/
    copied_task = tests_root / "sonobuoy" / "spread" / "kube-galaxy" / "task.yaml"
    assert copied_task.exists()
    assert "echo hi" in copied_task.read_text()


def test_sonobuoy_install_hook_overwrites_existing(tmp_path, monkeypatch, arch_info):
    """install_hook removes any pre-existing destination before copying."""
    monkeypatch.chdir(tmp_path)

    local_suite = tmp_path / "components" / "sonobuoy" / "spread" / "kube-galaxy"
    local_suite.mkdir(parents=True)
    (local_suite / "task.yaml").write_text("summary: new\nexecute: |\n  echo new\n")

    tests_root = tmp_path / "tests"
    # Pre-populate with stale content
    stale = tests_root / "sonobuoy" / "spread" / "kube-galaxy"
    stale.mkdir(parents=True)
    (stale / "stale.txt").write_text("old")

    monkeypatch.setattr(SystemPaths, "tests_root", lambda: tests_root)

    cfg = make_sonobuoy_config()
    manifest = Manifest(name="m", description="d", kubernetes_version="1.35.0")
    comp = Sonobuoy({}, manifest, cfg, arch_info)

    comp.install_hook()

    # Stale file should be gone; new task.yaml should be present
    assert not (stale / "stale.txt").exists()
    assert (stale / "task.yaml").exists()


def test_sonobuoy_remove_hook_deletes_suite_root(tmp_path, monkeypatch, arch_info):
    """remove_hook removes the suite root from tests_root."""
    tests_root = tmp_path / "tests"
    suite = tests_root / "sonobuoy" / "spread" / "kube-galaxy"
    suite.mkdir(parents=True)
    (suite / "task.yaml").write_text("execute: |\n  echo x\n")

    monkeypatch.setattr(SystemPaths, "tests_root", lambda: tests_root)

    cfg = make_sonobuoy_config()
    manifest = Manifest(name="m", description="d", kubernetes_version="1.35.0")
    comp = Sonobuoy({}, manifest, cfg, arch_info)

    comp.remove_hook()

    assert not (tests_root / "sonobuoy").exists()


def test_sonobuoy_remove_hook_is_idempotent(tmp_path, monkeypatch, arch_info):
    """remove_hook does not raise when the suite root does not exist."""
    tests_root = tmp_path / "tests"
    tests_root.mkdir()
    monkeypatch.setattr(SystemPaths, "tests_root", lambda: tests_root)

    cfg = make_sonobuoy_config()
    manifest = Manifest(name="m", description="d", kubernetes_version="1.35.0")
    comp = Sonobuoy({}, manifest, cfg, arch_info)

    # Should not raise even if suite doesn't exist
    comp.remove_hook()
