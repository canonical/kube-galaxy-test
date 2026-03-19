"""Path creation utilities shared across kube-galaxy modules."""

from pathlib import Path


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
