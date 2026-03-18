"""URL utilities.

Provides helper functions for constructing HTTP headers for API requests.
"""

import urllib.parse
from collections.abc import Callable

from kube_galaxy.pkg.utils.logging import warning

HEADER_PROVIDER = Callable[..., dict[str, str]]
_HEADER_PROVIDERS: dict[str, HEADER_PROVIDER] = {}


def authentication_headers() -> dict[str, str]:
    """Construct a dictionary of authentication headers for known services based
    on environment variables.
    """
    headers = {}
    for provider_host, func in _HEADER_PROVIDERS.items():
        if not provider_host.startswith("."):
            if auth := func().get("Authorization"):
                headers[provider_host] = auth
    if not headers:
        warning("No authentication headers found for any registered providers")
    return headers


def http_headers(url: str, **kwargs: bool | str) -> dict[str, str]:
    """Construct standard headers for requests, including authentication if available.

    Args:
        url: The URL for which to construct headers. This is used to determine
             if any registered header providers apply.
        **kwargs: Additional keyword arguments that may be passed to header providers.

    Returns:
        A dictionary of HTTP headers to include in requests to the given URL.
    """
    headers = {"User-Agent": "kube-galaxy"}
    url_parts = urllib.parse.urlparse(url)
    host = url_parts.hostname
    if host:
        for provider_host, func in _HEADER_PROVIDERS.items():
            if provider_host == host:
                # Exact match takes precedence
                headers.update(func(**kwargs))
                break
            if provider_host.startswith(".") and host.endswith(provider_host):
                # Subdomain match
                headers.update(func(**kwargs))
                break
    return headers


def register_headers_provider(*hosts: str) -> Callable[[HEADER_PROVIDER], HEADER_PROVIDER]:
    """Decorator to register a function as a headers provider for a specific host."""

    def decorator(func: HEADER_PROVIDER) -> HEADER_PROVIDER:
        for host in hosts:
            _HEADER_PROVIDERS[host] = func
        return func

    return decorator
