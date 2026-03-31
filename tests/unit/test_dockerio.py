"""Unit tests for kube_galaxy.pkg.utils.dockerio."""

import base64
from unittest.mock import patch

from kube_galaxy.pkg.utils.dockerio import dh_auth_basic, dh_http_headers


def _basic(username: str, token: str) -> str:
    """Return the expected Basic auth header value for given credentials."""
    return "Basic " + base64.b64encode(f"{username}:{token}".encode()).decode()


# ---------------------------------------------------------------------------
# dh_auth_basic
# ---------------------------------------------------------------------------


class TestDhAuthBasic:
    def test_returns_empty_when_no_env_vars(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", None),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", None),
        ):
            assert dh_auth_basic() == ""

    def test_returns_empty_when_only_username_set(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", "user"),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", None),
        ):
            assert dh_auth_basic() == ""

    def test_returns_empty_when_only_token_set(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", None),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", "tok"),
        ):
            assert dh_auth_basic() == ""

    def test_returns_basic_auth_when_both_set(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", "user"),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", "tok"),
        ):
            assert dh_auth_basic() == _basic("user", "tok")

    def test_credentials_are_base64_encoded(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", "alice"),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", "s3cr3t"),
        ):
            result = dh_auth_basic()
        assert result.startswith("Basic ")
        decoded = base64.b64decode(result[len("Basic ") :]).decode()
        assert decoded == "alice:s3cr3t"


# ---------------------------------------------------------------------------
# dh_http_headers
# ---------------------------------------------------------------------------


class TestDhHttpHeaders:
    def test_returns_default_headers_without_credentials(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", None),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", None),
        ):
            headers = dh_http_headers()

        assert "Authorization" not in headers

    def test_no_auth_header_without_basic_auth_kwarg(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", "user"),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", "tok"),
        ):
            headers = dh_http_headers()

        assert "Authorization" not in headers

    def test_basic_auth_kwarg_adds_authorization_header(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", "user"),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", "tok"),
        ):
            headers = dh_http_headers(basic_auth=True)

        assert headers["Authorization"] == _basic("user", "tok")

    def test_basic_auth_kwarg_without_credentials_omits_authorization(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", None),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", None),
        ):
            headers = dh_http_headers(basic_auth=True)

        assert "Authorization" not in headers

    def test_raw_kwarg_changes_accept_header(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", None),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", None),
        ):
            headers = dh_http_headers(raw=True)

        assert headers["Accept"] == "application/vnd.docker.raw+json"

    def test_raw_and_basic_auth_combined(self) -> None:
        with (
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_USERNAME", "user"),
            patch("kube_galaxy.pkg.utils.dockerio.DOCKERHUB_TOKEN", "tok"),
        ):
            headers = dh_http_headers(raw=True, basic_auth=True)

        assert headers["Accept"] == "application/vnd.docker.raw+json"
        assert headers["Authorization"] == _basic("user", "tok")
