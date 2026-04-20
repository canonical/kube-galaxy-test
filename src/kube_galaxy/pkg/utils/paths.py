"""Path creation utilities shared across kube-galaxy modules."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.loader import deserialize_manifest
from kube_galaxy.pkg.manifest.merger import merge_manifests
from kube_galaxy.pkg.manifest.validator import validate_manifest


def ensure_dir(path: Path) -> Path:
    """Create *path* (and all missing parents) if it does not yet exist.

    Equivalent to ``path.mkdir(parents=True, exist_ok=True)`` but provides
    a single named function so that all directory-creation in the project
    goes through one place.

    Args:
        path: Directory to create.

    Returns:
        *path*, so the call can be chained: ``ensure_dir(d) / "file.txt"``.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_active_manifest(
    manifest_path: str,
    overlays: Sequence[str] | None = None,
    *,
    provider_image: str | None = None,
) -> Path:
    """Write the active-manifest file, merging any overlays on top of the base.

    When *overlays* are provided they are deep-merged onto *manifest_path* in
    order (later overlays win).  The merged result is validated before writing.

    Without overlays the base manifest is loaded, validated, and written
    unchanged — so behaviour is consistent regardless of whether overlays are
    used.

    Args:
        manifest_path: Path (relative or absolute) to the base manifest file.
        overlays: Optional ordered sequence of overlay YAML file paths.
        provider_image: Optional override for the provider base image
            (e.g. ``ubuntu:22.04``).  Applied after overlays.

    Returns:
        The :class:`~pathlib.Path` of the written active-manifest file.
    """
    merged: dict[str, Any]
    if overlays:
        merged = merge_manifests(manifest_path, overlays)
    else:
        base = Path(manifest_path).resolve()
        with base.open() as f:
            merged = yaml.safe_load(f)
        manifest = deserialize_manifest(merged, base)
        validate_manifest(manifest)

    if provider_image:
        merged.setdefault("provider", {})["image"] = provider_image

    active = SystemPaths.active_manifest_path()
    active.parent.mkdir(parents=True, exist_ok=True)
    if active.exists() or active.is_symlink():
        active.unlink()
    with active.open("w") as f:
        yaml.dump(merged, f, sort_keys=False)
    return active


def get_active_manifest() -> Path | None:
    """Return the path of the active-manifest file, or *None*.

    Returns *None* when the file does not exist.  Dangling legacy symlinks
    (from pre-overlay-feature setups) also return *None* because
    :meth:`~pathlib.Path.exists` is ``False`` for them.

    Returns:
        :class:`~pathlib.Path` of the active manifest, or *None*.
    """
    path = SystemPaths.active_manifest_path()
    if path.exists():
        return path.resolve()
    return None
