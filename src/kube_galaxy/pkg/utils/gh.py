"""GitHub Actions integration utilities.

Provides helper functions for outputting values to GitHub Actions workflow
environments using the GITHUB_OUTPUT mechanism for inter-step communication.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

from kube_galaxy.pkg.utils.errors import ComponentError

# GitHub Actions sets this environment variable pointing to the output file
GITHUB_OUTPUT = os.getenv("GITHUB_OUTPUT")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


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


def gh_download_artifact(comp_name: str, src: str, dest: Path) -> None:
    """Download a GitHub Actions artifact from the current repository.

    Uses the GitHub REST API to find an artifact by name and download it
    as a zip archive, then extracts the specified file from the archive to the destination path.

    Args:
        comp_name: Component name (used in error messages)
        src: Artifact name to search for
        dest: Local file path to save the file of the same name from the head of the archive

    Raises:
        ComponentError: If not running in GitHub Actions, GITHUB_TOKEN is
            missing, the artifact is not found, or the download fails
        FileNotFoundError: If the specified file is not found in the downloaded artifact
    """
    if not GITHUB_OUTPUT:
        raise ComponentError(
            f"{comp_name} can only download artifacts from within a GitHub Actions workflow"
        )

    if not GITHUB_TOKEN:
        raise ComponentError(f"{comp_name} requires GITHUB_TOKEN to download artifacts")

    if not GITHUB_REPOSITORY:
        raise ComponentError(f"{comp_name} requires GITHUB_REPOSITORY to be set")

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Find the artifact by name using the REST API.
    list_url = (
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/artifacts"
        f"?name={urllib.parse.quote(src)}&per_page=1"
    )
    try:
        req = urllib.request.Request(list_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            data: dict[str, object] = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise ComponentError(f"{comp_name}: failed to list artifacts: HTTP {exc.code}") from exc

    artifacts = data.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        raise ComponentError(f"{comp_name}: no artifact named '{src}' found in {GITHUB_REPOSITORY}")

    artifact_id = artifacts[0]["id"]
    # dest is a path  /opt/kube-galaxy/<comp>/temp/the-file
    # the-file is expected to be at the root of the zip archive, so it is
    # extracted directly to dest.
    # we can leave the unextracted zip archive in the temp directory
    archive = dest.parent / f"{src}.zip"
    dest.mkdir(parents=True, exist_ok=True)

    # Download the artifact zip archive.
    download_url = (
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/artifacts/{artifact_id}/zip"
    )
    try:
        req = urllib.request.Request(download_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            archive.write_bytes(resp.read())
    except urllib.error.HTTPError as exc:
        raise ComponentError(
            f"{comp_name}: failed to download artifact '{src}': HTTP {exc.code}"
        ) from exc

    # Extract the specified file from the archive to the destination path.
    with zipfile.ZipFile(archive, "r") as zip_ref:
        try:
            with zip_ref.open(dest.name) as src_file, open(dest, "wb") as dest_file:
                dest_file.write(src_file.read())
        except KeyError:
            raise FileNotFoundError(
                f"{comp_name}: file '{dest.name}' not found in artifact '{src}'"
            ) from None
