"""GitHub Actions integration utilities.

Provides helper functions for outputting values to GitHub Actions workflow
environments using the GITHUB_OUTPUT mechanism for inter-step communication.
"""

import io
import os
import typing
import uuid
import zipfile
from pathlib import Path

import requests
from github import Auth, Github, GithubException
from github.Artifact import Artifact

from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.url import http_headers

# GitHub Actions sets this environment variable pointing to the output file
GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS")
GITHUB_OUTPUT = os.getenv("GITHUB_OUTPUT")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if typing.TYPE_CHECKING:
    # Define a Reader protocol for type hinting (io.Reader is not yet in mypy stubs)
    # This shouldn't be required past Python 3.14 when io.Reader is added,
    # but we can define it here for compatibility.
    class Reader(typing.Protocol):
        def read(self, size: int = -1, /) -> bytes: ...


def _write_chunked(infile: "Reader", outfile: io.BufferedWriter) -> None:
    """Write data to a file in chunks to handle large content without loading it all into memory."""
    while chunk := infile.read(8192):
        outfile.write(chunk)


def gh_output(name: str, value: str) -> None:
    """Output a value for use in subsequent GitHub Actions workflow steps.

    Writes key-value pairs to the GITHUB_OUTPUT file, enabling communication
    between different steps in a GitHub Actions workflow. If GITHUB_OUTPUT
    is not set (e.g., running outside GitHub Actions), this function is a no-op.

    GitHub Actions requires multiline values to be written using the EOF
    delimiter syntax. If `value` contains newlines this function will write
    the value using a unique delimiter to avoid breaking the workflow.

    Args:
        name: The output variable name (used as the key in workflow context)
        value: The output value to set (accessible as steps.<step-id>.outputs.<name>)

    Example:
        gh_output("cluster_id", "my-cluster-123")
        # In subsequent workflow steps: ${{ steps.<step-id>.outputs.cluster_id }}
    """
    if not GITHUB_OUTPUT:
        return

    # Single-line values can be written in the simple key=value form.
    if "\n" not in value:
        with open(GITHUB_OUTPUT, "a") as f:
            f.write(f"{name}={value}\n")
        return

    # For multiline values use the EOF delimiter form. Choose a delimiter
    # that is unlikely to appear in the value (UUID-based) to be safe.
    delim = f"DELIM_{uuid.uuid4().hex}"
    with open(GITHUB_OUTPUT, "a") as f:
        f.write(f"{name}<<{delim}\n")
        f.write(value)
        # Ensure a trailing newline before the closing delimiter.
        if not value.endswith("\n"):
            f.write("\n")
        f.write(f"{delim}\n")


def gh_list_artifacts_by_name(artifact_name: str) -> list[Artifact]:
    """List GitHub Actions artifacts in the current repository matching a name.

    Args:
        artifact_name: The name of the artifact to search for.
    Returns:
        A list of Artifact objects matching the specified name.
    """
    try:
        g = Github(auth=Auth.Token(GITHUB_TOKEN or ""))
        repo = g.get_repo(GITHUB_REPOSITORY or "")
        matching_artifacts = [
            a for a in repo.get_artifacts(name=artifact_name) if a.name == artifact_name
        ]
    except GithubException as exc:
        raise ComponentError(f"Failed to list artifacts for '{artifact_name}': {exc}") from exc

    if not matching_artifacts:
        raise ComponentError(f"No artifact named '{artifact_name}' found in {GITHUB_REPOSITORY}")
    return matching_artifacts


def gh_download_artifact(artifact: Artifact, dest: Path) -> Path:
    """Download a GitHub Actions artifact zip archive.

    Args:
        artifact: The Artifact object (from gh_list_artifacts_by_name)
        dest: The directory to download the artifact zip file to

    Returns:
        The path to the downloaded artifact zip file
    """
    archive = dest / f"{artifact.name}-{uuid.uuid4().hex}.zip"

    # The archive_download_url redirects to a signed S3 URL. Use allow_redirects=False
    # to capture the redirect location, then fetch it without the auth header so the
    # token is not forwarded to the third-party storage endpoint.
    try:
        redirect = requests.get(
            artifact.archive_download_url,
            headers=http_headers(artifact.archive_download_url),
            allow_redirects=False,
            timeout=30,
        )
        redirect.raise_for_status()
        download_url = redirect.headers.get("Location", artifact.archive_download_url)
        with requests.get(download_url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(archive, "wb") as dest_file:
                _write_chunked(resp.raw, dest_file)
    except requests.RequestException as exc:
        raise ComponentError(f"Failed to download artifact '{artifact.name}': {exc}") from exc
    return archive


def gh_extract_artifact_file(url: str, dest: Path) -> None:
    """Download a file from a GitHub Actions artifact.

    Parses a ``gh-artifact://artifact-name/path/in/zip`` URL, fetches the
    named artifact from the current repository via the GitHub REST API,
    downloads the zip archive, and extracts ``path/in/zip`` to ``dest``.

    Args:
        url: Full ``gh-artifact://artifact-name/path/to/file`` URL.
        dest: Local path to write the extracted file to.

    Raises:
        ComponentError: If not running in GitHub Actions, TOKEN/REPOSITORY env
            vars are missing, the artifact is not found, or download fails.
        FileNotFoundError: If the zip-internal path is not found in the artifact.
    """
    if GITHUB_ACTIONS != "true":
        raise ComponentError(
            "gh-artifact:// sources can only be used within a GitHub Actions workflow"
        )

    if not GITHUB_TOKEN:
        raise ComponentError("gh-artifact:// requires GITHUB_TOKEN to be set")

    if not GITHUB_REPOSITORY:
        raise ComponentError("gh-artifact:// requires GITHUB_REPOSITORY to be set")

    # Parse gh-artifact://artifact-name/path/to/file
    without_scheme = url[len("gh-artifact://") :]
    artifact_name, _, zip_path = without_scheme.partition("/")

    if not artifact_name or not zip_path:
        raise ComponentError(
            "Malformed gh-artifact URL; expected format "
            "'gh-artifact://<artifact-name>/<path/inside/zip>'"
        )

    artifacts = gh_list_artifacts_by_name(artifact_name)
    newest_artifact = max(
        artifacts,
        key=lambda a: a.updated_at or a.created_at,
    )

    # Download the artifact zip archive.
    archive = gh_download_artifact(newest_artifact, dest.parent)

    # Extract the specified path from the archive to dest.
    try:
        with zipfile.ZipFile(archive, "r") as zip_ref:
            try:
                with zip_ref.open(zip_path) as src_file, open(dest, "wb") as dest_file:
                    _write_chunked(src_file, dest_file)
            except KeyError:
                raise FileNotFoundError(
                    f"Path '{zip_path}' not found in artifact '{artifact_name}'"
                ) from None
    finally:
        # Best effort to clean up the downloaded archive file.
        try:
            archive.unlink()
        except Exception:
            pass
