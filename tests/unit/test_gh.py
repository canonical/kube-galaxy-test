"""Unit tests for kube_galaxy.pkg.utils.gh."""

import io
import typing
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib
from github import GithubException

from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.gh import (
    gh_download_artifact,
    gh_extract_artifact_file,
    gh_list_artifacts_by_name,
    gh_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_artifact(
    name: str = "my-artifact",
    artifact_id: int = 42,
    updated_at: datetime | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    """Return a mock Artifact with the fields used by gh.py."""
    a = MagicMock()
    a.name = name
    a.id = artifact_id
    a.archive_download_url = (
        f"https://api.github.com/repos/org/repo/actions/artifacts/{artifact_id}/zip"
    )
    a.updated_at = updated_at or datetime(2024, 1, 2, tzinfo=UTC)
    a.created_at = created_at or datetime(2024, 1, 1, tzinfo=UTC)
    return a


def _make_zip(zip_path: str, content: bytes = b"file-content") -> bytes:
    """Return bytes of a zip archive containing one file at zip_path."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zip_path, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# gh_output
# ---------------------------------------------------------------------------


class TestGhOutput:
    def test_noop_when_no_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        # Patch the module-level constant (already read at import time)
        with patch("kube_galaxy.pkg.utils.gh.GITHUB_OUTPUT", None):
            gh_output("key", "value")  # must not raise or write anything

    def test_single_line(self, tmp_path: Path) -> None:
        out_file = tmp_path / "github_output"
        out_file.write_text("")
        with patch("kube_galaxy.pkg.utils.gh.GITHUB_OUTPUT", str(out_file)):
            gh_output("cluster", "my-cluster")
        assert out_file.read_text() == "cluster=my-cluster\n"

    def test_multiline_uses_delimiter(self, tmp_path: Path) -> None:
        out_file = tmp_path / "github_output"
        out_file.write_text("")
        with patch("kube_galaxy.pkg.utils.gh.GITHUB_OUTPUT", str(out_file)):
            gh_output("body", "line1\nline2")
        content = out_file.read_text()
        lines = content.splitlines()
        # First line: body<<DELIM_...
        assert lines[0].startswith("body<<DELIM_")
        delim = lines[0][len("body<<") :]
        assert lines[1] == "line1"
        assert lines[2] == "line2"
        assert lines[3] == delim

    def test_multiline_adds_trailing_newline(self, tmp_path: Path) -> None:
        out_file = tmp_path / "github_output"
        out_file.write_text("")
        with patch("kube_galaxy.pkg.utils.gh.GITHUB_OUTPUT", str(out_file)):
            gh_output("body", "no-trailing-newline")
        content = out_file.read_text()
        # value has no newline so it's written as single-line form
        assert "no-trailing-newline" in content


# ---------------------------------------------------------------------------
# gh_list_artifacts_by_name
# ---------------------------------------------------------------------------


class TestGhListArtifactsByName:
    def test_returns_matching_artifacts(self) -> None:
        artifact = _make_artifact("my-artifact")
        mock_repo = MagicMock()
        mock_repo.get_artifacts.return_value = [artifact]
        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_repo

        with (
            patch("kube_galaxy.pkg.utils.gh.Github", return_value=mock_github),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_REPOSITORY", "org/repo"),
        ):
            result = gh_list_artifacts_by_name("my-artifact")

        assert result == [artifact]
        mock_github.get_repo.assert_called_once_with("org/repo")
        mock_repo.get_artifacts.assert_called_once_with(name="my-artifact")

    def test_filters_out_non_matching_names(self) -> None:
        """API may return artifacts with other names; filter to exact match only."""
        good = _make_artifact("my-artifact")
        bad = _make_artifact("my-artifact-extra")
        mock_repo = MagicMock()
        mock_repo.get_artifacts.return_value = [good, bad]
        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_repo

        with (
            patch("kube_galaxy.pkg.utils.gh.Github", return_value=mock_github),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_REPOSITORY", "org/repo"),
        ):
            result = gh_list_artifacts_by_name("my-artifact")

        assert result == [good]

    def test_raises_component_error_when_none_found(self) -> None:
        mock_repo = MagicMock()
        mock_repo.get_artifacts.return_value = []
        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_repo

        with (
            patch("kube_galaxy.pkg.utils.gh.Github", return_value=mock_github),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_REPOSITORY", "org/repo"),
            pytest.raises(ComponentError, match="No artifact named 'missing'"),
        ):
            gh_list_artifacts_by_name("missing")

    def test_raises_component_error_on_github_exception(self) -> None:
        mock_github = MagicMock()
        mock_github.get_repo.side_effect = GithubException(403, "Forbidden", None)

        with (
            patch("kube_galaxy.pkg.utils.gh.Github", return_value=mock_github),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_REPOSITORY", "org/repo"),
            pytest.raises(ComponentError, match="Failed to list artifacts"),
        ):
            gh_list_artifacts_by_name("some-artifact")


# ---------------------------------------------------------------------------
# gh_download_artifact
# ---------------------------------------------------------------------------


class TestGhDownloadArtifact:
    def test_downloads_and_returns_archive_path(self, tmp_path: Path) -> None:
        artifact = _make_artifact("my-artifact", artifact_id=7)
        zip_bytes = _make_zip("data.txt", b"hello")

        # First request: redirect response
        redirect_resp = MagicMock()
        redirect_resp.headers = {"Location": "https://s3.example.com/archive.zip"}
        redirect_resp.raise_for_status = MagicMock()

        # Second request: actual zip download as a context manager
        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.raw.read.side_effect = [zip_bytes, b""]
        download_resp.__enter__ = lambda s: s
        download_resp.__exit__ = MagicMock(return_value=False)

        with (
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch(
                "kube_galaxy.pkg.utils.gh.requests.get",
                side_effect=[redirect_resp, download_resp],
            ),
        ):
            archive = gh_download_artifact(artifact, tmp_path)

        assert archive.parent == tmp_path
        assert archive.name.startswith("my-artifact-")
        assert archive.suffix == ".zip"
        assert archive.read_bytes() == zip_bytes

    def test_falls_back_to_original_url_when_no_location_header(self, tmp_path: Path) -> None:
        artifact = _make_artifact("art", artifact_id=1)
        artifact.archive_download_url = (
            "https://api.github.com/repos/org/repo/actions/artifacts/1/zip"
        )
        zip_bytes = _make_zip("f.txt")

        redirect_resp = MagicMock()
        redirect_resp.headers = {}  # no Location header
        redirect_resp.raise_for_status = MagicMock()

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.raw.read.side_effect = [zip_bytes, b""]
        download_resp.__enter__ = lambda s: s
        download_resp.__exit__ = MagicMock(return_value=False)

        calls: list[str] = []

        def fake_get(url: str, **kwargs: object) -> MagicMock:
            calls.append(url)
            return redirect_resp if kwargs.get("allow_redirects") is False else download_resp

        with (
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch("kube_galaxy.pkg.utils.gh.requests.get", side_effect=fake_get),
        ):
            gh_download_artifact(artifact, tmp_path)

        # Second call should use the original URL as fallback
        assert calls[1] == artifact.archive_download_url

    def test_raises_component_error_on_http_error(self, tmp_path: Path) -> None:
        artifact = _make_artifact("art")

        with (
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch(
                "kube_galaxy.pkg.utils.gh.requests.get",
                side_effect=requests_lib.RequestException("timeout"),
            ),
            pytest.raises(ComponentError, match="Failed to download artifact 'art'"),
        ):
            gh_download_artifact(artifact, tmp_path)


# ---------------------------------------------------------------------------
# gh_extract_artifact_file
# ---------------------------------------------------------------------------


class TestGhExtractArtifactFile:
    _ENV: typing.ClassVar[dict[str, str]] = {
        "kube_galaxy.pkg.utils.gh.GITHUB_ACTIONS": "true",
        "kube_galaxy.pkg.utils.gh.GITHUB_TOKEN": "tok",
        "kube_galaxy.pkg.utils.gh.GITHUB_REPOSITORY": "org/repo",
    }

    def test_happy_path_extracts_file(self, tmp_path: Path) -> None:
        artifact = _make_artifact("my-artifact")
        zip_bytes = _make_zip("path/to/file.txt", b"extracted!")
        archive = tmp_path / "my-artifact-abc.zip"
        archive.write_bytes(zip_bytes)
        dest = tmp_path / "output" / "file.txt"
        dest.parent.mkdir()

        with (
            patch("kube_galaxy.pkg.utils.gh.GITHUB_ACTIONS", "true"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_REPOSITORY", "org/repo"),
            patch("kube_galaxy.pkg.utils.gh.gh_list_artifacts_by_name", return_value=[artifact]),
            patch("kube_galaxy.pkg.utils.gh.gh_download_artifact", return_value=archive),
        ):
            gh_extract_artifact_file("gh-artifact://my-artifact/path/to/file.txt", dest)

        assert dest.read_bytes() == b"extracted!"

    def test_raises_when_not_in_github_actions(self, tmp_path: Path) -> None:
        with (
            patch("kube_galaxy.pkg.utils.gh.GITHUB_ACTIONS", "false"),
            pytest.raises(ComponentError, match="GitHub Actions workflow"),
        ):
            gh_extract_artifact_file("gh-artifact://art/f.txt", tmp_path / "out")

    def test_raises_when_no_token(self, tmp_path: Path) -> None:
        with (
            patch("kube_galaxy.pkg.utils.gh.GITHUB_ACTIONS", "true"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", None),
            pytest.raises(ComponentError, match="GITHUB_TOKEN"),
        ):
            gh_extract_artifact_file("gh-artifact://art/f.txt", tmp_path / "out")

    def test_raises_when_no_repository(self, tmp_path: Path) -> None:
        with (
            patch("kube_galaxy.pkg.utils.gh.GITHUB_ACTIONS", "true"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_REPOSITORY", None),
            pytest.raises(ComponentError, match="GITHUB_REPOSITORY"),
        ):
            gh_extract_artifact_file("gh-artifact://art/f.txt", tmp_path / "out")

    def test_raises_on_malformed_url(self, tmp_path: Path) -> None:
        with (
            patch("kube_galaxy.pkg.utils.gh.GITHUB_ACTIONS", "true"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_REPOSITORY", "org/repo"),
            pytest.raises(ComponentError, match="Malformed gh-artifact URL"),
        ):
            gh_extract_artifact_file("gh-artifact://no-path-here", tmp_path / "out")

    def test_raises_file_not_found_when_path_missing_in_zip(self, tmp_path: Path) -> None:
        artifact = _make_artifact("art")
        zip_bytes = _make_zip("other/file.txt", b"data")
        archive = tmp_path / "art-abc.zip"
        archive.write_bytes(zip_bytes)
        dest = tmp_path / "output.txt"

        with (
            patch("kube_galaxy.pkg.utils.gh.GITHUB_ACTIONS", "true"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_REPOSITORY", "org/repo"),
            patch("kube_galaxy.pkg.utils.gh.gh_list_artifacts_by_name", return_value=[artifact]),
            patch("kube_galaxy.pkg.utils.gh.gh_download_artifact", return_value=archive),
            pytest.raises(FileNotFoundError, match=r"missing/path\.txt"),
        ):
            gh_extract_artifact_file("gh-artifact://art/missing/path.txt", dest)

    def test_picks_newest_artifact_by_updated_at(self, tmp_path: Path) -> None:
        older = _make_artifact("art", artifact_id=1, updated_at=datetime(2024, 1, 1, tzinfo=UTC))
        newer = _make_artifact("art", artifact_id=2, updated_at=datetime(2024, 6, 1, tzinfo=UTC))
        zip_bytes = _make_zip("f.txt", b"data")
        archive = tmp_path / "art-abc.zip"
        archive.write_bytes(zip_bytes)
        dest = tmp_path / "out.txt"

        captured: list[MagicMock] = []

        def fake_download(artifact: MagicMock, dest_dir: Path) -> Path:
            captured.append(artifact)
            return archive

        with (
            patch("kube_galaxy.pkg.utils.gh.GITHUB_ACTIONS", "true"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_TOKEN", "tok"),
            patch("kube_galaxy.pkg.utils.gh.GITHUB_REPOSITORY", "org/repo"),
            patch(
                "kube_galaxy.pkg.utils.gh.gh_list_artifacts_by_name",
                return_value=[older, newer],
            ),
            patch("kube_galaxy.pkg.utils.gh.gh_download_artifact", side_effect=fake_download),
        ):
            gh_extract_artifact_file("gh-artifact://art/f.txt", dest)

        assert captured[0].id == 2  # newer artifact selected
