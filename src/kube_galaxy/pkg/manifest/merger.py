"""Manifest deep-merge utilities for kube-galaxy."""

from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from kube_galaxy.pkg.manifest.loader import deserialize_manifest
from kube_galaxy.pkg.manifest.validator import validate_manifest


def _is_named_list(lst: list[Any]) -> bool:
    """Return True iff *lst* is non-empty and every element is a dict with a 'name' key.

    An empty list returns False — intent is ambiguous so the caller falls through
    to the existing replace behaviour.
    """
    if not lst:
        return False
    return all(isinstance(item, dict) and "name" in item for item in lst)


def _merge_named_list(base: list[Any], overlay: list[Any]) -> list[Any]:
    """Merge two named lists by matching the 'name' key.

    - An overlay entry whose ``name`` matches a base entry is deep-merged onto
      that base entry in-place (positional order preserved).
    - An overlay entry whose ``name`` is not present in the base is appended.
    - An overlay entry without a ``name`` is appended as-is (degenerate case).

    Neither *base* nor *overlay* is mutated.

    Args:
        base: Base list of named dicts.
        overlay: Overlay list applied on top.

    Returns:
        New merged list.
    """
    result: list[Any] = [deepcopy(item) for item in base]
    base_index: dict[str, int] = {
        item["name"]: i
        for i, item in enumerate(result)
        if isinstance(item, dict) and "name" in item
    }
    for overlay_item in overlay:
        if not isinstance(overlay_item, dict) or "name" not in overlay_item:
            result.append(deepcopy(overlay_item))
            continue
        name = overlay_item["name"]
        if name in base_index:
            idx = base_index[name]
            result[idx] = deep_merge(result[idx], overlay_item)
        else:
            result.append(deepcopy(overlay_item))
    return result


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *overlay* on top of *base*.

    Rules:

    - Both values are dicts → recurse into the nested dict.
    - Both values are named lists (every element is a dict with a ``name`` key)
      → merge by name: matching entries are deep-merged, new names are appended.
    - Otherwise (scalar, unnamed list, new key) → overlay value wins; unnamed
      lists are replaced entirely, not appended.
    - Neither *base* nor *overlay* is mutated.

    Args:
        base: Base dictionary.
        overlay: Overlay dictionary whose values take precedence.

    Returns:
        A new dict representing the merged result.
    """
    result = deepcopy(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        elif (
            key in result
            and isinstance(result[key], list)
            and isinstance(value, list)
            and _is_named_list(result[key])
            and _is_named_list(value)
        ):
            result[key] = _merge_named_list(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def merge_manifests(
    base_path: str | Path,
    overlay_paths: Sequence[str | Path],
) -> dict[str, Any]:
    """Load *base_path*, fold each overlay in order, validate, and return merged dict.

    Each overlay is deep-merged onto the accumulated result left to right, so
    later overlays take precedence over earlier ones.  Only dict-valued keys are
    merged recursively; scalars and lists are replaced outright.

    The merged result is validated through :func:`deserialize_manifest` and
    :func:`validate_manifest` before being returned, so callers can be sure the
    result represents a well-formed manifest.

    Args:
        base_path: Path to the base manifest YAML file.
        overlay_paths: Sequence of overlay YAML file paths applied in order.
            Can be empty — in that case the base manifest is loaded, validated,
            and returned unchanged.

    Returns:
        Raw merged YAML dict ready for serialisation.

    Raises:
        FileNotFoundError: If any path does not exist.
        yaml.YAMLError: If any file contains invalid YAML.
        ValueError: If the merged result fails manifest validation.
    """
    base_path = Path(base_path)
    with base_path.open() as f:
        merged: dict[str, Any] = yaml.safe_load(f)

    if not isinstance(merged, dict):
        raise ValueError("Base manifest must be a YAML dictionary")

    for overlay_path in overlay_paths:
        with Path(overlay_path).open() as f:
            overlay_data: dict[str, Any] = yaml.safe_load(f)
        if not isinstance(overlay_data, dict):
            raise ValueError(f"Overlay '{overlay_path}' must be a YAML dictionary")
        merged = deep_merge(merged, overlay_data)

    manifest = deserialize_manifest(merged, base_path)
    validate_manifest(manifest)
    return merged
