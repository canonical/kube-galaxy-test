"""
Utilities for component installation and management.
"""

import hashlib
import shutil
import tarfile
import urllib.request
from pathlib import Path

import chevron

from kube_galaxy.pkg.arch.detector import ArchInfo
from kube_galaxy.pkg.literals import Commands, Permissions, SystemPaths
from kube_galaxy.pkg.manifest.models import ComponentConfig, RepoInfo
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.gh import gh_download_artifact
from kube_galaxy.pkg.utils.shell import run


def download_file(url: str, dest: Path, verify_sha256: str | None = None) -> None:
    """
    Download a file from URL to destination.

    Supports ``https://``, ``http://``, and ``file://`` URLs via
    :func:`urllib.request.urlretrieve`, and ``gh-artifact://`` URLs via
    :func:`~kube_galaxy.pkg.utils.gh.gh_download_artifact`.

    Args:
        url: File URL (https://, http://, file://, or gh-artifact://)
        dest: Destination path
        verify_sha256: Optional SHA256 checksum to verify (ignored for gh-artifact://)

    Raises:
        ComponentError: If download fails or checksum mismatch
    """

    dest.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("gh-artifact://"):
        gh_download_artifact(url, dest)
        return

    try:
        urllib.request.urlretrieve(url, dest)

        if verify_sha256:
            actual_sha256 = compute_sha256(dest)
            if actual_sha256 != verify_sha256:
                raise ComponentError(
                    f"SHA256 mismatch for {dest.name}: "
                    f"expected {verify_sha256}, got {actual_sha256}"
                )
    except Exception as e:
        raise ComponentError(f"Failed to download {url}: {e}") from e


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    """
    Extract tar.gz or tar.bz2 archive.

    Args:
        archive_path: Path to archive
        dest_dir: Destination directory

    Raises:
        ComponentError: If extraction fails
    """
    try:
        with tarfile.open(archive_path) as tar:
            tar.extractall(dest_dir)
    except Exception as e:
        raise ComponentError(f"Failed to extract {archive_path.name}: {e}") from e


def install_binary(
    binary_path: Path,
    binary_name: str,
    component_name: str,
) -> str:
    """
    Install a binary to component directory and register with update-alternatives.

    Args:
        binary_path: Path to the binary
        binary_name: Name of the binary (e.g., 'containerd')
        component_name: Component name for directory structure

    Raises:
        ComponentError: If installation fails
    """
    # Use component-specific directory
    dest_dir = SystemPaths.component_bin_dir(component_name)
    try:
        # Create directory and install binary
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / binary_name
        shutil.copyfile(binary_path, dest_path)
        dest_path.chmod(0o755)

        # Register with update-alternatives
        alternative_path = f"{SystemPaths.USR_LOCAL_BIN}/{binary_name}"
        run(
            [
                *Commands.UPDATE_ALTERNATIVES_INSTALL,
                alternative_path,
                binary_name,
                str(dest_path),
                Permissions.ALTERNATIVES_PRIORITY,
            ],
            check=True,
        )
        return alternative_path
    except Exception as e:
        raise ComponentError(f"Failed to install {binary_name} to {dest_dir}: {e}") from e


def remove_binary(binary_name: str, dest_dir: Path = Path(SystemPaths.USR_LOCAL_BIN)) -> None:
    """
    Remove a binary from a directory.

    Args:
        binary_name: Name of the binary
        dest_dir: Directory containing the binary

    Raises:
        ComponentError: If removal fails
    """
    try:
        dest_path = dest_dir / binary_name
        if dest_path.exists():
            dest_path.unlink()
    except Exception as e:
        raise ComponentError(f"Failed to remove {binary_name} from {dest_dir}: {e}") from e


def format_component_pattern(
    filename_pattern: str,
    config: ComponentConfig,
    arch_info: ArchInfo,
    repo: RepoInfo | None = None,
) -> str:
    """Construct a resolved URL or path from a Mustache ``source-format`` template.

    Templates use Mustache ``{{ variable }}`` syntax rendered via the
    ``chevron`` library.  Chevron performs nested dict lookups using ``dot``
    notation, so ``{{ repo.base-url }}`` naturally resolves the ``"base-url"``
    key inside the ``repo`` context dict — no preprocessing is required.

    ``repo.subdir`` is itself rendered as a Mustache template with ``name`` in
    context before being placed into the data dict, so it may contain
    ``{{ name }}`` to derive the subdirectory from the component name.

    Supported template variables:

    - ``{{ name }}``           - component name (e.g. ``sonobuoy``)
    - ``{{ arch }}``           - Kubernetes architecture name (e.g. ``amd64``)
    - ``{{ release }}``        - component release tag (e.g. ``2.1.0``)
    - ``{{ ref }}``            - git ref override, or empty string
    - ``{{ repo.base-url }}``  -
    - ``{{ repo.subdir }}``    - optional subdirectory within the repo (may
                                 itself contain ``{{ name }}``)
    - ``{{ repo.ref }}``       - git ref from repo config, or empty string

    Args:
        filename_pattern: The ``source-format`` template string from the manifest.
        config: Component configuration (provides ``name``, ``release``, ``arch``).
        arch_info: Architecture information.
        repo: Repository context for ``{{ repo.* }}`` variables.  When *None*,
              an empty :class:`~kube_galaxy.pkg.manifest.models.RepoInfo` is
              used (all ``{{ repo.* }}`` variables expand to empty strings).

    Returns:
        The fully-resolved string with all placeholders substituted.
    """
    effective_repo = repo if repo is not None else RepoInfo()

    # Pre-render repo.subdir so {{ name }} within it is expanded first.
    # Fall back to empty string when subdir is None to avoid passing None to chevron.render.
    raw_subdir = effective_repo.subdir or ""
    subdir = str(chevron.render(raw_subdir, {"name": config.name}))

    base_url = effective_repo.base_url
    if base_url.startswith("local://"):
        fragment = base_url[len("local://") :]
        base_url = (Path.cwd() / fragment).as_uri()

    data = {
        "name": config.name,
        "arch": arch_info.k8s,
        "release": config.release,
        "ref": effective_repo.ref or "",
        "repo": {
            "base-url": base_url,
            "subdir": subdir,
            "ref": effective_repo.ref or "",
        },
    }
    return str(chevron.render(filename_pattern, data))
