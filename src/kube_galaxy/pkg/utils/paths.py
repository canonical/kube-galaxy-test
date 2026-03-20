"""Path creation utilities shared across kube-galaxy modules."""

from pathlib import Path

from kube_galaxy.pkg.literals import SystemPaths


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


def set_active_manifest(manifest_path: str) -> None:
    """Create or update the active-manifest symlink in the current directory.

    The symlink always points to the absolute (resolved) path of
    *manifest_path* so that it remains valid regardless of the working
    directory from which subsequent commands are invoked.

    Args:
        manifest_path: Path (relative or absolute) to the manifest file.
    """
    link = SystemPaths.active_manifest_link()
    target = Path(manifest_path).resolve()
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(target)


def get_active_manifest() -> Path | None:
    """Return the resolved target of the active-manifest symlink, or *None*.

    Returns *None* when the symlink does not exist or its target has been
    removed (dangling symlink).

    Returns:
        Resolved :class:`~pathlib.Path` of the active manifest, or *None*.
    """
    link = SystemPaths.active_manifest_link()
    if link.is_symlink() and link.exists():
        return link.resolve()
    return None
