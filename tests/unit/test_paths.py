"""Unit tests for kube_galaxy.pkg.utils.paths helpers."""

import yaml

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.utils.paths import create_active_manifest, get_active_manifest

_MINIMAL_MANIFEST = """\
name: test-cluster
kubernetes-version: "1.35.0"
"""

_MINIMAL_MANIFEST_2 = """\
name: second-cluster
kubernetes-version: "1.35.0"
"""


def test_create_active_manifest_creates_real_file(tmp_path, monkeypatch):
    """create_active_manifest writes a real YAML file (not a symlink)."""
    monkeypatch.chdir(tmp_path)

    manifest = tmp_path / "manifests" / "baseline.yaml"
    manifest.parent.mkdir()
    manifest.write_text(_MINIMAL_MANIFEST)

    create_active_manifest(str(manifest))

    active = SystemPaths.active_manifest_path()
    assert active.is_file()
    assert not active.is_symlink()


def test_create_active_manifest_returns_path(tmp_path, monkeypatch):
    """create_active_manifest returns the path of the written file."""
    monkeypatch.chdir(tmp_path)

    manifest = tmp_path / "baseline.yaml"
    manifest.write_text(_MINIMAL_MANIFEST)

    result = create_active_manifest(str(manifest))

    assert result == SystemPaths.active_manifest_path()


def test_create_active_manifest_writes_valid_yaml(tmp_path, monkeypatch):
    """create_active_manifest writes YAML content that round-trips correctly."""
    monkeypatch.chdir(tmp_path)

    manifest = tmp_path / "baseline.yaml"
    manifest.write_text(_MINIMAL_MANIFEST)

    create_active_manifest(str(manifest))

    active = SystemPaths.active_manifest_path()
    data = yaml.safe_load(active.read_text())
    assert data["name"] == "test-cluster"
    assert data["kubernetes-version"] == "1.35.0"


def test_create_active_manifest_replaces_existing_file(tmp_path, monkeypatch):
    """create_active_manifest overwrites the previously written active-manifest file."""
    monkeypatch.chdir(tmp_path)

    first = tmp_path / "first.yaml"
    first.write_text(_MINIMAL_MANIFEST)
    second = tmp_path / "second.yaml"
    second.write_text(_MINIMAL_MANIFEST_2)

    create_active_manifest(str(first))
    create_active_manifest(str(second))

    active = SystemPaths.active_manifest_path()
    data = yaml.safe_load(active.read_text())
    assert data["name"] == "second-cluster"


def test_get_active_manifest_returns_path_to_written_file(tmp_path, monkeypatch):
    """get_active_manifest returns the path of the active-manifest file."""
    monkeypatch.chdir(tmp_path)

    manifest = tmp_path / "manifests" / "baseline.yaml"
    manifest.parent.mkdir()
    manifest.write_text(_MINIMAL_MANIFEST)

    create_active_manifest(str(manifest))

    result = get_active_manifest()
    assert result is not None
    assert result == SystemPaths.active_manifest_path().resolve()


def test_get_active_manifest_returns_none_when_no_file(tmp_path, monkeypatch):
    """get_active_manifest returns None when no active-manifest file exists."""
    monkeypatch.chdir(tmp_path)

    assert get_active_manifest() is None


def test_get_active_manifest_returns_none_when_file_deleted(tmp_path, monkeypatch):
    """get_active_manifest returns None after the active-manifest file is removed."""
    monkeypatch.chdir(tmp_path)

    manifest = tmp_path / "baseline.yaml"
    manifest.write_text(_MINIMAL_MANIFEST)
    create_active_manifest(str(manifest))

    SystemPaths.active_manifest_path().unlink()

    assert get_active_manifest() is None


def test_get_active_manifest_backward_compat_symlink(tmp_path, monkeypatch):
    """get_active_manifest resolves a legacy symlink left by pre-overlay-feature setups."""
    monkeypatch.chdir(tmp_path)

    target = tmp_path / "baseline.yaml"
    target.write_text(_MINIMAL_MANIFEST)

    # Manually create a symlink as the old code would have done
    active = SystemPaths.active_manifest_path()
    active.parent.mkdir(parents=True, exist_ok=True)
    active.symlink_to(target)

    result = get_active_manifest()
    assert result is not None
    assert result == target.resolve()


def test_get_active_manifest_returns_none_for_dangling_symlink(tmp_path, monkeypatch):
    """get_active_manifest returns None for a dangling legacy symlink."""
    monkeypatch.chdir(tmp_path)

    target = tmp_path / "gone.yaml"
    target.write_text(_MINIMAL_MANIFEST)

    active = SystemPaths.active_manifest_path()
    active.parent.mkdir(parents=True, exist_ok=True)
    active.symlink_to(target)
    target.unlink()  # dangling symlink

    assert get_active_manifest() is None


def test_create_active_manifest_with_single_overlay(tmp_path, monkeypatch):
    """Overlay scalar value is visible in the written active-manifest file."""
    monkeypatch.chdir(tmp_path)

    base = tmp_path / "base.yaml"
    base.write_text(_MINIMAL_MANIFEST)

    overlay = tmp_path / "overlay.yaml"
    overlay.write_text('kubernetes-version: "1.36.0"\n')

    create_active_manifest(str(base), [str(overlay)])

    active = SystemPaths.active_manifest_path()
    data = yaml.safe_load(active.read_text())
    assert data["kubernetes-version"] == "1.36.0"
    assert data["name"] == "test-cluster"  # inherited from base


def test_create_active_manifest_with_multiple_overlays_last_wins(tmp_path, monkeypatch):
    """Later overlay takes precedence over earlier ones."""
    monkeypatch.chdir(tmp_path)

    base = tmp_path / "base.yaml"
    base.write_text(_MINIMAL_MANIFEST)

    ov1 = tmp_path / "ov1.yaml"
    ov1.write_text('kubernetes-version: "1.36.0"\n')
    ov2 = tmp_path / "ov2.yaml"
    ov2.write_text('kubernetes-version: "1.37.0"\n')

    create_active_manifest(str(base), [str(ov1), str(ov2)])

    active = SystemPaths.active_manifest_path()
    data = yaml.safe_load(active.read_text())
    assert data["kubernetes-version"] == "1.37.0"


def test_create_active_manifest_overlay_merges_nested_dict(tmp_path, monkeypatch):
    """Overlay updates a nested dict key while leaving sibling keys intact."""
    monkeypatch.chdir(tmp_path)

    base = tmp_path / "base.yaml"
    base.write_text(
        """\
name: test-cluster
kubernetes-version: "1.35.0"
provider:
  type: lxd
  nodes:
    control-plane: 1
    worker: 2
"""
    )

    overlay = tmp_path / "overlay.yaml"
    overlay.write_text("provider:\n  nodes:\n    worker: 5\n")

    create_active_manifest(str(base), [str(overlay)])

    active = SystemPaths.active_manifest_path()
    data = yaml.safe_load(active.read_text())
    assert data["provider"]["nodes"]["worker"] == 5
    assert data["provider"]["nodes"]["control-plane"] == 1  # sibling preserved
    assert data["provider"]["type"] == "lxd"  # sibling preserved


def test_create_active_manifest_overlay_merges_named_list(tmp_path, monkeypatch):
    """Overlay entry matching by name is merged; new entries are appended."""
    monkeypatch.chdir(tmp_path)

    base = tmp_path / "base.yaml"
    base.write_text(
        """\
name: test-cluster
kubernetes-version: "1.35.0"
networking:
  - name: default
    service-cidr: "10.96.0.0/12"
    pod-cidr: "192.168.0.0/16"
"""
    )

    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        """\
networking:
  - name: custom
    service-cidr: "10.0.0.0/16"
    pod-cidr: "10.244.0.0/16"
"""
    )

    create_active_manifest(str(base), [str(overlay)])

    active = SystemPaths.active_manifest_path()
    data = yaml.safe_load(active.read_text())
    # "custom" is a new name → appended alongside base "default" entry
    assert len(data["networking"]) == 2
    names = [e["name"] for e in data["networking"]]
    assert "default" in names
    assert "custom" in names
