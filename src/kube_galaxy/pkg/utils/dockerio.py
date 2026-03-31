"""Dockerhub integration utilities.

Provides helper functions for constructing authentication headers for Docker
registries based on environment variables and Docker config files.
"""

import base64
import os

from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.url import register_headers_provider

DOCKERHUB_USERNAME = os.getenv("DOCKERHUB_USERNAME")
DOCKERHUB_TOKEN = os.getenv("DOCKERHUB_TOKEN")


def dh_auth_basic() -> str:
    """Construct a Basic auth header for Dockerhub authentication from
    * DOCKERHUB_USERNAME and DOCKERHUB_TOKEN

    Returns:
        A string in the format Basic <base64-encoded credentials> otherwise an empty string.
    """
    username, password = None, None
    if DOCKERHUB_USERNAME and DOCKERHUB_TOKEN:
        info("    Using DOCKERHUB_USERNAME and DOCKERHUB_TOKEN for docker.io authentication")
        username, password = DOCKERHUB_USERNAME, DOCKERHUB_TOKEN
    if username and password:
        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"
    return ""


@register_headers_provider("docker.io")
def dh_http_headers(**kwargs: bool | str) -> dict[str, str]:
    """Construct standard headers for docker.io requests, including authentication if available."""
    headers = {}
    if kwargs.get("raw"):
        headers["Accept"] = "application/vnd.docker.raw+json"
    if kwargs.get("basic_auth") and (gh_auth := dh_auth_basic()):
        headers["Authorization"] = gh_auth

    return headers
