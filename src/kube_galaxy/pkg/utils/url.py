"""URL utilities.

Provides helper functions for constructing HTTP headers for API requests.
"""

import os
import urllib.parse

# Authentication token for GitHub API requests, read from the GITHUB_TOKEN environment variable.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def http_headers(url: str, **kwargs: bool | str) -> dict[str, str]:
    """Construct standard headers for GitHub API requests, including authentication if available."""
    headers = {
        "User-Agent": "kube-galaxy",
    }

    url_parts = urllib.parse.urlparse(url)
    host = url_parts.hostname
    if host and (host == "github.com" or host.endswith(".github.com")):
        # For GitHub API requests, include the API version and authentication token if available.
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        headers["Accept"] = "application/vnd.github+json"
        if kwargs.get("raw"):
            headers["Accept"] = "application/vnd.github.raw+json"
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    return headers
