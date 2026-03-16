"""GitHub Actions integration utilities.

Provides helper functions for outputting values to GitHub Actions workflow
environments using the GITHUB_OUTPUT mechanism for inter-step communication.
"""

import io
import json
import os
import typing
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

from kube_galaxy.pkg.utils.errors import ComponentError

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


def gh_download_artifact(url: str, dest: Path) -> None:
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

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kube-galaxy/gh-artifact",
    }

    # Find the artifact by name using the REST API, paging through results and
    # selecting the newest matching artifact deterministically.
    per_page = 100
    page = 1
    matching_artifacts: list[dict[str, object]] = []

    while True:
        list_url = (
            f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/artifacts"
            f"?name={urllib.parse.quote(artifact_name)}&per_page={per_page}&page={page}"
        )
        try:
            req = urllib.request.Request(list_url, headers=headers)
            with urllib.request.urlopen(req) as resp:
                data: dict[str, object] = json.loads(resp.read())
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ComponentError(f"Failed to list artifacts for '{artifact_name}': {exc}") from exc

        artifacts = data.get("artifacts", [])
        if not isinstance(artifacts, list):
            break

        # Filter by exact name to be robust even if the API returns extra entries.
        for artifact in artifacts:
            if isinstance(artifact, dict) and artifact.get("name") == artifact_name:
                matching_artifacts.append(artifact)

        if len(artifacts) < per_page:
            # No more pages.
            break

        page += 1

    if not matching_artifacts:
        raise ComponentError(f"No artifact named '{artifact_name}' found in {GITHUB_REPOSITORY}")

    def _artifact_sort_key(artifact: dict[str, object]) -> str:
        # Prefer updated_at, fall back to created_at, then empty string.
        updated_at = artifact.get("updated_at")
        created_at = artifact.get("created_at")
        for value in (updated_at, created_at):
            if isinstance(value, str):
                return value
        return ""

    newest_artifact = sorted(
        matching_artifacts,
        key=_artifact_sort_key,
        reverse=True,
    )[0]
    artifact_id = newest_artifact["id"]
    archive = dest.parent / f"{artifact_name}-{uuid.uuid4().hex}.zip"

    # Download the artifact zip archive.
    download_url = (
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/artifacts/{artifact_id}/zip"
    )
    try:
        req = urllib.request.Request(download_url, headers=headers)
        with urllib.request.urlopen(req) as src_file, open(archive, "wb") as dest_file:
            _write_chunked(src_file, dest_file)
    except urllib.error.URLError as exc:
        raise ComponentError(
            f"Failed to download artifact '{artifact_name}': HTTP {exc.reason}"
        ) from exc

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
