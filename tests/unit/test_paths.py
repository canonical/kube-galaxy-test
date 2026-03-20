"""Unit tests for kube_galaxy.pkg.utils.paths helpers."""

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.utils.paths import get_active_manifest, set_active_manifest


def test_set_active_manifest_creates_symlink(tmp_path, monkeypatch):
    """set_active_manifest creates a symlink pointing at the resolved manifest path."""
    monkeypatch.chdir(tmp_path)

    manifest = tmp_path / "manifests" / "baseline.yaml"
    manifest.parent.mkdir()
    manifest.write_text("name: test\n")

    set_active_manifest(str(manifest))

    link = SystemPaths.active_manifest_link()
    assert link.is_symlink()
    assert link.resolve() == manifest.resolve()


def test_set_active_manifest_replaces_existing_symlink(tmp_path, monkeypatch):
    """set_active_manifest replaces a pre-existing symlink."""
    monkeypatch.chdir(tmp_path)

    first = tmp_path / "first.yaml"
    first.write_text("name: first\n")
    second = tmp_path / "second.yaml"
    second.write_text("name: second\n")

    set_active_manifest(str(first))
    set_active_manifest(str(second))

    link = SystemPaths.active_manifest_link()
    assert link.resolve() == second.resolve()


def test_get_active_manifest_returns_resolved_path(tmp_path, monkeypatch):
    """get_active_manifest returns the resolved path after set_active_manifest."""
    monkeypatch.chdir(tmp_path)

    manifest = tmp_path / "manifests" / "baseline.yaml"
    manifest.parent.mkdir()
    manifest.write_text("name: test\n")

    set_active_manifest(str(manifest))

    result = get_active_manifest()
    assert result is not None
    assert result == manifest.resolve()


def test_get_active_manifest_returns_none_when_no_link(tmp_path, monkeypatch):
    """get_active_manifest returns None when no symlink exists."""
    monkeypatch.chdir(tmp_path)

    assert get_active_manifest() is None


def test_get_active_manifest_returns_none_for_dangling_symlink(tmp_path, monkeypatch):
    """get_active_manifest returns None when the symlink target has been removed."""
    monkeypatch.chdir(tmp_path)

    target = tmp_path / "gone.yaml"
    target.write_text("name: gone\n")
    set_active_manifest(str(target))
    target.unlink()  # remove the target → dangling symlink

    assert get_active_manifest() is None
