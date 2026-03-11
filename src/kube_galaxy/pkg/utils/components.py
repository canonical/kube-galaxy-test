"""
Utilities for component installation and management.
"""

import hashlib
import shutil
import tarfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment

from kube_galaxy.pkg.arch.detector import ArchInfo
from kube_galaxy.pkg.literals import Commands, Permissions, SystemPaths
from kube_galaxy.pkg.manifest.models import ComponentConfig
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.shell import run


def download_file(url: str, dest: Path, verify_sha256: str | None = None) -> None:
    """
    Download a file from URL to destination.

    Args:
        url: File URL
        dest: Destination path
        verify_sha256: Optional SHA256 checksum to verify

    Raises:
        ComponentError: If download fails or checksum mismatch
    """
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


@dataclass
class _RepoContext:
    """Context object for Jinja2 template rendering of repo-related placeholders.

    Attributes:
        base_url: Repository base URL.  For local sources this is the string
            representation of the current working directory.
        subdir:   Optional subdirectory within the repo (empty string if unset).
        ref:      Optional git reference override (empty string if unset).
    """

    base_url: str
    subdir: str = field(default="")
    ref: str = field(default="")


def format_component_pattern(
    filename_pattern: str, config: ComponentConfig, arch_info: ArchInfo
) -> str:
    """Construct a resolved URL or path from a Jinja2 ``source-format`` template.

    Templates use standard Jinja2 ``{{ variable }}`` syntax.

    Supported template variables:

    - ``{{ arch }}``           - Kubernetes architecture name (e.g. ``amd64``)
    - ``{{ release }}``        - component release tag (e.g. ``2.1.0``)
    - ``{{ ref }}``            - git ref override, or empty string
    - ``{{ repo.base_url }}``  - repository base URL, or ``str(Path.cwd())`` for
                                 local sources
    - ``{{ repo.subdir }}``    - optional subdirectory within the repo
    - ``{{ repo.ref }}``       - git ref from repo config, or empty string

    Args:
        filename_pattern: The ``source-format`` template string from the manifest.
        config: Component configuration.
        arch_info: Architecture information.

    Returns:
        The fully-resolved string with all placeholders substituted.
    """
    env = Environment(autoescape=False)
    template = env.from_string(filename_pattern)
    repo = _RepoContext(
        base_url=str(Path.cwd()) if config.repo.is_local else config.repo.base_url,
        subdir=config.repo.subdir or "",
        ref=config.repo.ref or "",
    )
    return template.render(
        arch=arch_info.k8s,
        release=config.release,
        ref=config.repo.ref or "",
        repo=repo,
    )
