"""Tests for CLI lifecycle enforcement (Phase 7)."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kube_galaxy.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_ACTIVE_PATH = Path("/tmp/opt/kube-galaxy/active-manifest.yaml")
_RECOVERY_PATH = "manifests/baseline-k8s-1.35.yaml"


def _invoke(*args: str) -> CliRunner:
    return runner.invoke(app, list(args))


# ---------------------------------------------------------------------------
# test command
# ---------------------------------------------------------------------------


class TestTestCmd:
    def test_no_active_manifest_exits_with_error(self) -> None:
        with patch("kube_galaxy.cli.get_active_manifest", return_value=None):
            result = _invoke("test")
        assert result.exit_code == 1
        assert "No active manifest found" in result.output
        assert "kube-galaxy setup" in result.output

    def test_uses_active_manifest(self) -> None:
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=_ACTIVE_PATH),
            patch("kube_galaxy.cmd.test.spread") as mock_spread,
        ):
            result = _invoke("test")
        assert result.exit_code == 0
        mock_spread.assert_called_once_with(str(_ACTIVE_PATH))


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


class TestStatusCmd:
    def test_no_active_manifest_exits_with_error(self) -> None:
        with patch("kube_galaxy.cli.get_active_manifest", return_value=None):
            result = _invoke("status")
        assert result.exit_code == 1
        assert "No active manifest found" in result.output

    def test_uses_active_manifest(self) -> None:
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=_ACTIVE_PATH),
            patch("kube_galaxy.cmd.status.status") as mock_status,
        ):
            result = _invoke("status")
        assert result.exit_code == 0
        mock_status.assert_called_once_with(str(_ACTIVE_PATH), wait=False, timeout=300)

    def test_wait_and_timeout_forwarded(self) -> None:
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=_ACTIVE_PATH),
            patch("kube_galaxy.cmd.status.status") as mock_status,
        ):
            result = _invoke("status", "--wait", "--timeout", "60")
        assert result.exit_code == 0
        mock_status.assert_called_once_with(str(_ACTIVE_PATH), wait=True, timeout=60)


# ---------------------------------------------------------------------------
# logs command
# ---------------------------------------------------------------------------


class TestLogsCmd:
    def test_no_active_manifest_exits_with_error(self) -> None:
        with patch("kube_galaxy.cli.get_active_manifest", return_value=None):
            result = _invoke("logs")
        assert result.exit_code == 1
        assert "No active manifest found" in result.output

    def test_uses_active_manifest(self) -> None:
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=_ACTIVE_PATH),
            patch("kube_galaxy.cmd.logs.logs") as mock_logs,
        ):
            result = _invoke("logs")
        assert result.exit_code == 0
        mock_logs.assert_called_once_with(str(_ACTIVE_PATH))


# ---------------------------------------------------------------------------
# cleanup command — cluster target
# ---------------------------------------------------------------------------


class TestCleanupClusterCmd:
    def test_no_active_no_manifest_exits(self) -> None:
        with patch("kube_galaxy.cli.get_active_manifest", return_value=None):
            result = _invoke("cleanup", "cluster")
        assert result.exit_code == 1
        assert "No active manifest found" in result.output

    def test_uses_active_manifest(self) -> None:
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=_ACTIVE_PATH),
            patch("kube_galaxy.cmd.cleanup.cleanup_clusters") as mock_cleanup,
        ):
            result = _invoke("cleanup", "cluster")
        assert result.exit_code == 0
        mock_cleanup.assert_called_once_with(str(_ACTIVE_PATH), False, update_kubeconfig=False)

    def test_recovery_manifest_option_prints_warning(self) -> None:
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=None),
            patch("kube_galaxy.cmd.cleanup.cleanup_clusters"),
        ):
            result = _invoke("cleanup", "cluster", "--manifest", _RECOVERY_PATH)
        assert result.exit_code == 0
        assert "Warning" in result.output
        assert _RECOVERY_PATH in result.output

    def test_recovery_manifest_option_used_when_active_absent(self) -> None:
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=None),
            patch("kube_galaxy.cmd.cleanup.cleanup_clusters") as mock_cleanup,
        ):
            result = _invoke("cleanup", "cluster", "--manifest", _RECOVERY_PATH)
        assert result.exit_code == 0
        mock_cleanup.assert_called_once_with(_RECOVERY_PATH, False, update_kubeconfig=False)

    def test_recovery_manifest_takes_precedence_over_active(self) -> None:
        """Explicit --manifest overrides active manifest with a warning."""
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=_ACTIVE_PATH),
            patch("kube_galaxy.cmd.cleanup.cleanup_clusters") as mock_cleanup,
        ):
            result = _invoke("cleanup", "cluster", "--manifest", _RECOVERY_PATH)
        assert result.exit_code == 0
        assert "Warning" in result.output
        mock_cleanup.assert_called_once_with(_RECOVERY_PATH, False, update_kubeconfig=False)


# ---------------------------------------------------------------------------
# cleanup command — all target
# ---------------------------------------------------------------------------


class TestCleanupAllCmd:
    def test_no_active_no_manifest_exits(self) -> None:
        with patch("kube_galaxy.cli.get_active_manifest", return_value=None):
            result = _invoke("cleanup", "all")
        assert result.exit_code == 1
        assert "No active manifest found" in result.output

    def test_uses_active_manifest(self) -> None:
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=_ACTIVE_PATH),
            patch("kube_galaxy.cmd.cleanup.cleanup_all") as mock_cleanup,
        ):
            result = _invoke("cleanup", "all")
        assert result.exit_code == 0
        mock_cleanup.assert_called_once_with(str(_ACTIVE_PATH), False, update_kubeconfig=False)

    def test_recovery_manifest_option_warns_and_proceeds(self) -> None:
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=None),
            patch("kube_galaxy.cmd.cleanup.cleanup_all") as mock_cleanup,
        ):
            result = _invoke("cleanup", "all", "--manifest", _RECOVERY_PATH)
        assert result.exit_code == 0
        assert "Warning" in result.output
        mock_cleanup.assert_called_once_with(_RECOVERY_PATH, False, update_kubeconfig=False)


# ---------------------------------------------------------------------------
# cleanup command — files target (no manifest needed)
# ---------------------------------------------------------------------------


class TestCleanupFilesCmd:
    def test_no_active_manifest_still_works(self) -> None:
        with (
            patch("kube_galaxy.cli.get_active_manifest", return_value=None),
            patch("kube_galaxy.cmd.cleanup.cleanup_files") as mock_cleanup,
        ):
            result = _invoke("cleanup", "files")
        assert result.exit_code == 0
        mock_cleanup.assert_called_once_with()

    def test_unknown_target_exits(self) -> None:
        result = _invoke("cleanup", "unknown-target")
        assert result.exit_code == 1
        assert "Unknown cleanup target" in result.output


# ---------------------------------------------------------------------------
# setup command still accepts positional manifest
# ---------------------------------------------------------------------------


class TestSetupCmd:
    def test_manifest_argument_accepted(self) -> None:
        with patch("kube_galaxy.cmd.setup.setup") as mock_setup:
            result = _invoke("setup", "manifests/baseline-k8s-1.35.yaml")
        assert result.exit_code == 0
        mock_setup.assert_called_once_with(
            "manifests/baseline-k8s-1.35.yaml", update_kubeconfig=False, overlays=None
        )

    def test_overlay_option_forwarded(self) -> None:
        with patch("kube_galaxy.cmd.setup.setup") as mock_setup:
            result = _invoke(
                "setup",
                "manifests/baseline-k8s-1.35.yaml",
                "--overlay",
                "overlays/extra.yaml",
            )
        assert result.exit_code == 0
        mock_setup.assert_called_once_with(
            "manifests/baseline-k8s-1.35.yaml",
            update_kubeconfig=False,
            overlays=["overlays/extra.yaml"],
        )
