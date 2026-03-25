"""
Utilities for component installation and management.
"""

import hashlib
import tarfile
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import chevron

from kube_galaxy.pkg.literals import Permissions, SystemPaths, URLs
from kube_galaxy.pkg.manifest.models import ComponentConfig, RepoInfo
from kube_galaxy.pkg.utils.detector import ArchInfo
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.gh import gh_extract_artifact_file
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.url import http_headers

if TYPE_CHECKING:
    from kube_galaxy.pkg.units._base import Unit


def download_file(url: str, dest: Path, verify_sha256: str | None = None) -> None:
    """
    Download a file from URL to destination.

    Supports ``https://``, ``http://``, and ``file://`` URLs via
    :func:`urllib.request.urlopen`,

    Supports ``gh-artifact://`` URLs for GitHub Actions artifacts via
    :func:`~kube_galaxy.pkg.utils.gh.gh_extract_artifact_file`.

    Supports ``local://`` URLs as a convenient way to reference files relative
    to the current working directory without needing to specify a full path

    Args:
        url: File URL
        dest: Destination path
        verify_sha256: Optional SHA256 checksum to verify (ignored for gh-artifact://)

    Raises:
        ComponentError: If download fails or checksum mismatch
    """

    ensure_dir(dest.parent)
    if url.startswith("gh-artifact://"):
        gh_extract_artifact_file(url, dest)
        return

    if url.startswith("local://"):
        fragment = url[len("local://") :]
        working_dir = Path.cwd().resolve()
        resolved = (working_dir / fragment.strip("/")).resolve()
        # Prevent escaping the working directory via path traversal in the fragment
        if not resolved.is_relative_to(working_dir):
            raise ComponentError(
                f"Invalid local:// URL; path escapes working directory: {fragment!r}"
            )
        url = resolved.as_uri()

    try:
        req = urllib.request.Request(url, headers=http_headers(url, raw=True))
        with urllib.request.urlopen(req) as response, open(dest, "wb") as dest_file:
            while chunk := response.read(8192):
                dest_file.write(chunk)

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
    unit: "Unit",
) -> str:
    """
    Install a binary to the component directory on the unit and register with
    update-alternatives.

    The unit is instructed to download the binary from the orchestrator's
    staging area via :meth:`~kube_galaxy.pkg.units._base.Unit.staging_url`
    and :meth:`~kube_galaxy.pkg.units._base.Unit.download`.  For a
    :class:`~kube_galaxy.pkg.units.local.LocalUnit` this resolves to a
    ``file://`` URL; for remote units the artifact server must have been
    started and configured via
    :meth:`~kube_galaxy.pkg.units._base.Unit.set_artifact_server` before
    this function is called.

    All directory creation, permission setting, and update-alternatives
    registration are performed on the unit via ``unit.run()``.  No root
    access is required on the orchestrator.

    Args:
        binary_path: Local path to the binary in the orchestrator staging area.
        binary_name: Name of the binary (e.g., 'containerd')
        component_name: Component name for directory structure
        unit: Unit to install onto

    Raises:
        ComponentError: If installation fails
    """
    dest_dir = SystemPaths.component_bin_dir(component_name)
    dest_path = dest_dir / binary_name
    try:
        # Create directory on the unit
        unit.run(["mkdir", "-p", str(dest_dir)], privileged=True, check=True)

        # Fetch artifact from the orchestrator's staging area.
        # For LocalUnit this resolves to a file:// URL; for remote units the
        # artifact server must be started and configured via
        # unit.set_artifact_server() before calling install_binary.
        artifact_url = unit.staging_url(binary_path)
        unit.download(artifact_url, str(dest_path))
        unit.run(["chmod", "755", str(dest_path)], privileged=True, check=True)

        # Register with update-alternatives (requires elevated privileges)
        alternative_path = f"{SystemPaths.USR_LOCAL_BIN}/{binary_name}"
        unit.run(
            [
                "update-alternatives",
                "--install",
                alternative_path,
                binary_name,
                str(dest_path),
                Permissions.ALTERNATIVES_PRIORITY,
            ],
            privileged=True,
            check=True,
        )
        return alternative_path
    except Exception as e:
        raise ComponentError(f"Failed to install {binary_name} to {dest_dir}: {e}") from e


def remove_binary(binary_path: Path, unit: "Unit") -> None:
    """
    Remove a binary and its update-alternatives entry from the unit.

    Args:
        binary_path: Path to the binary on the unit
        unit: Unit to run privileged commands on
    """
    try:
        unit.run(
            ["update-alternatives", "--remove", binary_path.name, str(binary_path)],
            privileged=True,
            check=False,
        )
        unit.run(["rm", "-f", str(binary_path)], privileged=True, check=False)
    except Exception:
        pass  # Ignore errors during cleanup


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
    - ``{{ repo.base-url }}``  - repository base URL. (e.g. ``https://`` or ``local://`` or ``gh-artifact://``)
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

    data = {
        "name": config.name,
        "arch": arch_info.k8s,
        "release": config.release,
        "ref": effective_repo.ref or "",
        "repo": {
            "base-url": effective_repo.base_url,
            "subdir": subdir,
            "ref": effective_repo.ref or "",
        },
        "mirror": {"base-url": URLs.ORCHESTRATOR_HOST},
    }
    return str(chevron.render(filename_pattern, data))
