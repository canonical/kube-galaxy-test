"""Unit tests for kube_galaxy.pkg.manifest.merger."""

import pytest

from kube_galaxy.pkg.manifest.merger import (
    _is_named_list,
    _merge_named_list,
    deep_merge,
    merge_manifests,
)

_BASE_MANIFEST = """\
name: test-cluster
kubernetes-version: "1.35.0"
"""

_BASE_WITH_PROVIDER = """\
name: test-cluster
kubernetes-version: "1.35.0"
provider:
  type: lxd
  nodes:
    control-plane: 1
    worker: 2
"""

_BASE_WITH_NETWORKING = """\
name: test-cluster
kubernetes-version: "1.35.0"
networking:
  - name: default
    service-cidr: "10.96.0.0/12"
    pod-cidr: "192.168.0.0/16"
"""

_BASE_WITH_COMPONENTS = """\
name: test-cluster
kubernetes-version: "1.35.0"
components:
  - name: containerd
    category: containerd
    release: "2.2.1"
    installation:
      method: binary-archive
      repo:
        base-url: https://github.com/containerd/containerd
      source-format: "containerd-{{ release }}-linux-{{ arch }}.tar.gz"
  - name: runc
    category: containerd
    release: "1.3.4"
    installation:
      method: binary
      repo:
        base-url: https://github.com/opencontainers/runc
      source-format: "runc.{{ arch }}"
"""


# ---------------------------------------------------------------------------
# deep_merge unit tests
# ---------------------------------------------------------------------------


def test_deep_merge_scalar_override():
    """Overlay scalar value replaces the base scalar."""
    result = deep_merge({"a": 1}, {"a": 2})
    assert result["a"] == 2


def test_deep_merge_new_key():
    """Key present only in overlay appears in result."""
    result = deep_merge({"a": 1}, {"b": 2})
    assert result["a"] == 1
    assert result["b"] == 2


def test_deep_merge_nested_dict_recursive():
    """Nested dicts are merged recursively; sibling keys of the changed key survive."""
    base = {"outer": {"x": 1, "y": 2}}
    overlay = {"outer": {"x": 99}}
    result = deep_merge(base, overlay)
    assert result["outer"]["x"] == 99
    assert result["outer"]["y"] == 2  # sibling preserved


def test_deep_merge_list_replacement():
    """Unnamed list (no 'name' keys) is fully replaced — no append."""
    # integers have no 'name' key, so _is_named_list returns False → replace path
    base = {"items": [1, 2, 3]}
    overlay = {"items": [4, 5]}
    result = deep_merge(base, overlay)
    assert result["items"] == [4, 5]


def test_deep_merge_does_not_mutate_base():
    """deep_merge never modifies the input dicts."""
    base = {"a": {"b": 1}}
    overlay = {"a": {"b": 2}}
    _ = deep_merge(base, overlay)
    assert base["a"]["b"] == 1


def test_deep_merge_does_not_mutate_overlay():
    """deep_merge never modifies the overlay dict."""
    base = {"a": 1}
    overlay = {"b": {"nested": True}}
    _ = deep_merge(base, overlay)
    assert overlay["b"]["nested"] is True


def test_deep_merge_empty_overlay_returns_copy_of_base():
    """An empty overlay leaves base values unchanged."""
    base = {"a": 1, "b": {"c": 2}}
    result = deep_merge(base, {})
    assert result == base
    assert result is not base  # must be a copy


def test_deep_merge_empty_base_returns_copy_of_overlay():
    """An empty base gives a copy of the overlay."""
    overlay = {"x": 42}
    result = deep_merge({}, overlay)
    assert result == overlay
    assert result is not overlay


# ---------------------------------------------------------------------------
# Named-list helpers
# ---------------------------------------------------------------------------


def test_is_named_list_true_for_all_named_dicts():
    assert _is_named_list([{"name": "a"}, {"name": "b"}]) is True


def test_is_named_list_false_for_empty():
    assert _is_named_list([]) is False


def test_is_named_list_false_when_any_element_missing_name():
    assert _is_named_list([{"name": "a"}, {"x": 1}]) is False


def test_is_named_list_false_for_non_dicts():
    assert _is_named_list([1, 2, 3]) is False


def test_merge_named_list_preserves_order():
    """Base entry order is preserved; new overlay entries are appended at the end."""
    base = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    overlay = [{"name": "c", "extra": True}, {"name": "d"}]
    result = _merge_named_list(base, overlay)
    assert [e["name"] for e in result] == ["a", "b", "c", "d"]
    assert result[2]["extra"] is True


# ---------------------------------------------------------------------------
# Named-list merge via deep_merge
# ---------------------------------------------------------------------------


def test_deep_merge_named_list_changes_matching_entry():
    """Overlay entry matching by name deep-merges; unmentioned sibling fields survive."""
    base = {"items": [{"name": "foo", "x": 1, "y": 2}]}
    overlay = {"items": [{"name": "foo", "x": 99}]}
    result = deep_merge(base, overlay)
    assert result["items"][0]["x"] == 99
    assert result["items"][0]["y"] == 2  # sibling preserved
    assert len(result["items"]) == 1


def test_deep_merge_named_list_appends_new_entry():
    """Overlay entry with a new name is appended; base entries untouched."""
    base = {"items": [{"name": "foo", "v": 1}]}
    overlay = {"items": [{"name": "bar", "v": 2}]}
    result = deep_merge(base, overlay)
    assert len(result["items"]) == 2
    assert result["items"][0] == {"name": "foo", "v": 1}
    assert result["items"][1] == {"name": "bar", "v": 2}


def test_deep_merge_named_list_mixed_change_and_add():
    """Single overlay with one matching name (updated) and one new name (appended)."""
    base = {"items": [{"name": "a", "v": 1}, {"name": "b", "v": 2}]}
    overlay = {"items": [{"name": "a", "v": 99}, {"name": "c", "v": 3}]}
    result = deep_merge(base, overlay)
    assert len(result["items"]) == 3
    assert result["items"][0] == {"name": "a", "v": 99}
    assert result["items"][1] == {"name": "b", "v": 2}
    assert result["items"][2] == {"name": "c", "v": 3}


def test_deep_merge_empty_base_named_list_replaces():
    """Empty base list falls through to replace (_is_named_list([]) is False)."""
    base: dict[str, list[object]] = {"items": []}
    overlay = {"items": [{"name": "foo"}]}
    result = deep_merge(base, overlay)
    assert result["items"] == [{"name": "foo"}]


def test_deep_merge_named_list_does_not_mutate():
    """Named-list merge never modifies base or overlay inputs."""
    base = {"items": [{"name": "a", "v": 1}]}
    overlay = {"items": [{"name": "a", "v": 2}]}
    _ = deep_merge(base, overlay)
    assert base["items"][0]["v"] == 1
    assert overlay["items"][0]["v"] == 2


# ---------------------------------------------------------------------------
# merge_manifests integration tests
# ---------------------------------------------------------------------------


def test_merge_manifests_no_overlays_returns_base(tmp_path):
    """With an empty overlay list, merge_manifests returns the base dict unchanged."""
    base = tmp_path / "base.yaml"
    base.write_text(_BASE_MANIFEST)

    result = merge_manifests(base, [])
    assert result["name"] == "test-cluster"
    assert result["kubernetes-version"] == "1.35.0"


def test_merge_manifests_single_overlay_merges_correctly(tmp_path):
    """Single overlay scalar is reflected in the returned dict."""
    base = tmp_path / "base.yaml"
    base.write_text(_BASE_MANIFEST)

    ov = tmp_path / "ov.yaml"
    ov.write_text('kubernetes-version: "1.36.0"\n')

    result = merge_manifests(base, [str(ov)])
    assert result["kubernetes-version"] == "1.36.0"
    assert result["name"] == "test-cluster"  # base value preserved


def test_merge_manifests_multiple_overlays_chained_in_order(tmp_path):
    """Multiple overlays are applied left to right; the last one wins."""
    base = tmp_path / "base.yaml"
    base.write_text(_BASE_MANIFEST)

    ov1 = tmp_path / "ov1.yaml"
    ov1.write_text('kubernetes-version: "1.36.0"\n')
    ov2 = tmp_path / "ov2.yaml"
    ov2.write_text('kubernetes-version: "1.37.0"\n')

    result = merge_manifests(base, [str(ov1), str(ov2)])
    assert result["kubernetes-version"] == "1.37.0"


def test_merge_manifests_nested_dict_overlay(tmp_path):
    """Nested dict overlay changes a leaf while leaving sibling keys intact."""
    base = tmp_path / "base.yaml"
    base.write_text(_BASE_WITH_PROVIDER)

    ov = tmp_path / "ov.yaml"
    ov.write_text("provider:\n  nodes:\n    worker: 5\n")

    result = merge_manifests(base, [str(ov)])
    assert result["provider"]["nodes"]["worker"] == 5
    assert result["provider"]["nodes"]["control-plane"] == 1
    assert result["provider"]["type"] == "lxd"


def test_merge_manifests_named_list_changes_networking(tmp_path):
    """Named networking list merges by name; unmatched sibling fields survive."""
    base = tmp_path / "base.yaml"
    base.write_text(_BASE_WITH_NETWORKING)

    ov = tmp_path / "ov.yaml"
    ov.write_text(
        """\
networking:
  - name: default
    service-cidr: "10.0.0.0/16"
"""
    )

    result = merge_manifests(base, [str(ov)])
    assert len(result["networking"]) == 1
    assert result["networking"][0]["service-cidr"] == "10.0.0.0/16"
    assert result["networking"][0]["pod-cidr"] == "192.168.0.0/16"  # sibling preserved


def test_merge_manifests_networking_add_new_entry(tmp_path):
    """Overlay networking entry with a new name is appended."""
    base = tmp_path / "base.yaml"
    base.write_text(_BASE_WITH_NETWORKING)

    ov = tmp_path / "ov.yaml"
    ov.write_text(
        """\
networking:
  - name: extra
    service-cidr: "10.200.0.0/16"
    pod-cidr: "10.201.0.0/16"
"""
    )

    result = merge_manifests(base, [str(ov)])
    assert len(result["networking"]) == 2
    assert result["networking"][0]["name"] == "default"  # base entry preserved
    assert result["networking"][1]["name"] == "extra"


def test_merge_manifests_components_change(tmp_path):
    """Overlay changes a component release; all other components and sibling fields intact."""
    base = tmp_path / "base.yaml"
    base.write_text(_BASE_WITH_COMPONENTS)

    ov = tmp_path / "ov.yaml"
    ov.write_text('components:\n  - name: containerd\n    release: "2.3.0"\n')

    result = merge_manifests(base, [str(ov)])
    by_name = {c["name"]: c for c in result["components"]}
    assert by_name["containerd"]["release"] == "2.3.0"
    assert by_name["containerd"]["category"] == "containerd"  # sibling preserved
    assert by_name["runc"]["release"] == "1.3.4"  # untouched
    assert len(result["components"]) == 2


def test_merge_manifests_components_add(tmp_path):
    """Overlay adds a new component; total count is base count + 1."""
    base = tmp_path / "base.yaml"
    base.write_text(_BASE_WITH_COMPONENTS)

    ov = tmp_path / "ov.yaml"
    ov.write_text(
        """\
components:
  - name: crictl
    category: containerd
    release: "1.35.0"
    installation:
      method: binary-archive
      repo:
        base-url: https://github.com/kubernetes-sigs/cri-tools
      source-format: "crictl-v{{ release }}-linux-{{ arch }}.tar.gz"
"""
    )

    result = merge_manifests(base, [str(ov)])
    names = [c["name"] for c in result["components"]]
    assert "crictl" in names
    assert len(result["components"]) == 3


def test_merge_manifests_invalid_result_raises(tmp_path):
    """An overlay that produces an invalid manifest raises ValueError."""
    base = tmp_path / "base.yaml"
    base.write_text(_BASE_MANIFEST)

    # Remove the required kubernetes-version field
    ov = tmp_path / "ov.yaml"
    ov.write_text('kubernetes-version: ""\n')

    with pytest.raises(ValueError, match="kubernetes-version"):
        merge_manifests(base, [str(ov)])


def test_merge_manifests_base_not_found_raises(tmp_path):
    """FileNotFoundError when base path does not exist."""
    with pytest.raises(FileNotFoundError):
        merge_manifests(tmp_path / "missing.yaml", [])


def test_merge_manifests_overlay_not_found_raises(tmp_path):
    """FileNotFoundError when an overlay path does not exist."""
    base = tmp_path / "base.yaml"
    base.write_text(_BASE_MANIFEST)

    with pytest.raises(FileNotFoundError):
        merge_manifests(base, [str(tmp_path / "missing.yaml")])
