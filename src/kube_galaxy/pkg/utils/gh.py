"""GitHub Actions integration utilities.

Provides helper functions for outputting values to GitHub Actions workflow
environments using the GITHUB_OUTPUT mechanism for inter-step communication.
"""

import base64
import io
import os
import re
import typing
import uuid
import zipfile
from pathlib import Path

import requests
from github import Auth, Github, GithubException
from github.Artifact import Artifact

from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.url import http_headers, register_headers_provider

# GitHub Actions sets this environment variable pointing to the output file
GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS")
GITHUB_OUTPUT = os.getenv("GITHUB_OUTPUT")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_ACTOR = os.getenv("GITHUB_ACTOR")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

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


def gh_auth_bearer() -> str:
    """Construct a Bearer token for GitHub API authentication from GITHUB_TOKEN.

    Returns:
        A string in the format Bearer <token> if GITHUB_TOKEN is set, otherwise an empty string.
    """

    return f"Bearer {GITHUB_TOKEN}" if GITHUB_TOKEN else ""


def gh_auth_basic() -> str:
    """Construct a Basic auth header for GitHub API authentication from
    * GITHUB_USERNAME and GITHUB_TOKEN
    * GITHUB_ACTOR and GITHUB_TOKEN

    Returns:
        A string in the format Basic <base64-encoded credentials> otherwise an empty string.
    """
    username, password = None, None
    if GITHUB_USERNAME and GITHUB_TOKEN:
        info("    Using GITHUB_USERNAME and GITHUB_TOKEN for ghcr.io authentication")
        username, password = GITHUB_USERNAME, GITHUB_TOKEN
    elif GITHUB_ACTOR and GITHUB_TOKEN:
        info("    Using GITHUB_ACTOR and GITHUB_TOKEN for ghcr.io authentication")
        username, password = GITHUB_ACTOR, GITHUB_TOKEN
    if username and password:
        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"
    return ""


@register_headers_provider("github.com", ".github.com", "ghcr.io")
def gh_http_headers(**kwargs: bool | str) -> dict[str, str]:
    """Construct standard headers for GitHub API requests, including authentication if available.

    For GitHub API requests, include the API version and authentication token if available.
    """
    headers = {"X-GitHub-Api-Version": "2022-11-28", "Accept": "application/vnd.github+json"}
    if kwargs.get("raw"):
        headers["Accept"] = "application/vnd.github.raw+json"
    if bearer := gh_auth_bearer():
        headers["Authorization"] = bearer
    if kwargs.get("basic-auth") and (gh_auth := gh_auth_basic()):
        headers["Authorization"] = gh_auth

    return headers


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


def gh_download_release_asset(url: str, dest: Path) -> None:
    """Download a GitHub release asset from a private repository.

    Parses a ``https://github.com/{owner}/{repo}/releases/download/{tag}/{filename}``
    URL, uses the GitHub API via PyGithub to locate the asset by tag and filename,
    then downloads the asset via ``api.github.com`` with ``Accept: application/octet-stream``.

    This is required for private repositories where the standard browser-download URL
    does not support programmatic Bearer-token authentication.

    Args:
        url: Full GitHub release download URL
            (``https://github.com/{owner}/{repo}/releases/download/{tag}/{filename}``).
        dest: Local path to write the downloaded asset to.

    Raises:
        ComponentError: If GITHUB_TOKEN is not set, the release or asset is not found,
            or the download fails.
    """
    if not GITHUB_TOKEN:
        raise ComponentError(
            f"GITHUB_TOKEN is required to download release assets from private GitHub "
            f"repositories. Set GITHUB_TOKEN to a PAT with 'repo' scope and retry.\n"
            f"  URL: {url}"
        )

    # Parse https://github.com/{owner}/{repo}/releases/download/{tag}/{filename}
    match = re.match(r"https://github\.com/([^/]+/[^/]+)/releases/download/([^/]+)/(.+)$", url)
    if not match:
        raise ComponentError(
            f"Unrecognised GitHub release download URL format: {url!r}\n"
            f"Expected: https://github.com/{{owner}}/{{repo}}/releases/download/{{tag}}/{{filename}}"
        )
    repo_name, tag, filename = match.group(1), match.group(2), match.group(3)

    try:
        g = Github(auth=Auth.Token(GITHUB_TOKEN))
        repo = g.get_repo(repo_name)
        # Draft releases are not returned by /releases/tags/{tag} — we must
        # list all releases and find the one whose tag_name matches.
        release = None
        for r in repo.get_releases():
            if r.tag_name == tag:
                release = r
                break
        if release is None:
            raise ComponentError(
                f"No release with tag '{tag}' found in '{repo_name}' "
                f"(checked published and draft releases)"
            )
        assets = list(release.get_assets())
    except GithubException as exc:
        raise ComponentError(f"Failed to look up release '{tag}' in '{repo_name}': {exc}") from exc

    asset = next((a for a in assets if a.name == filename), None)
    if asset is None:
        available = ", ".join(a.name for a in assets)
        raise ComponentError(
            f"Asset '{filename}' not found in release '{tag}' of '{repo_name}'.\n"
            f"Available assets: {available}"
        )

    # Download via the GitHub API endpoint with Accept: application/octet-stream.
    # Use allow_redirects=False to capture the redirect to the signed storage URL,
    # then fetch that URL without auth headers to avoid token leakage to third-party
    # storage (same two-step pattern as gh_download_artifact).
    api_url = f"https://api.github.com/repos/{repo_name}/releases/assets/{asset.id}"
    api_headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/octet-stream",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        redirect = requests.get(api_url, headers=api_headers, allow_redirects=False, timeout=30)
        redirect.raise_for_status()
        download_url = redirect.headers.get("Location", api_url)
        with requests.get(download_url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as dest_file:
                _write_chunked(resp.raw, dest_file)
    except requests.RequestException as exc:
        raise ComponentError(
            f"Failed to download asset '{filename}' from '{repo_name}': {exc}"
        ) from exc


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
