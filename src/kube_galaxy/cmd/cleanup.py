"""Cleanup command handler."""

import shutil
from pathlib import Path

import typer

from kube_galaxy.pkg.cluster import teardown_cluster
from kube_galaxy.pkg.literals import FilePatterns, SystemPaths, TestDirectories
from kube_galaxy.pkg.utils.kubeconfig import (
    KUBE_GALAXY_CONTEXT,
    context_exists,
    is_interactive,
    remove_kube_galaxy_context,
)
from kube_galaxy.pkg.utils.logging import error, info, section, success


def cleanup_files() -> None:
    """Clean up temporary files and test artifacts."""
    section("Cleaning Up Temporary Files")

    cleanup_paths = [
        TestDirectories.TEST_RESULTS,
        TestDirectories.SPREAD_RESULTS,
        TestDirectories.DEBUG_LOGS,
        TestDirectories.CLEANUP_LOGS,
        TestDirectories.ISSUE_DATA,
        FilePatterns.TEST_CLUSTER_CONFIG,
    ]

    for path_str in cleanup_paths:
        path = Path(path_str)
        try:
            if path.is_dir():
                shutil.rmtree(path)
                info(f"Removed directory: {path}")
            elif path.is_file():
                path.unlink()
                info(f"Removed file: {path}")
        except Exception as e:
            error(f"Failed to remove {path}: {e}")

    # Clean up log files
    for log_file in Path(".").glob("*.log"):
        try:
            log_file.unlink()
            info(f"Removed file: {log_file}")
        except Exception as e:
            error(f"Failed to remove {log_file}: {e}")

    # Remove the active-manifest file so subsequent commands require an explicit manifest
    active_link = SystemPaths.active_manifest_path()
    if active_link.exists() or active_link.is_symlink():
        try:
            active_link.unlink()
            info(f"Removed active manifest link: {active_link}")
        except Exception as e:
            error(f"Failed to remove active manifest link {active_link}: {e}")

    # Remove the local orchestrator staging tree (cwd/tmp)
    staging = SystemPaths.staging_root()
    if staging.exists():
        try:
            shutil.rmtree(staging)
            info(f"Removed staging directory: {staging}")
        except Exception as e:
            error(f"Failed to remove staging directory {staging}: {e}")

    success("File cleanup completed!")


def cleanup_clusters(
    manifest_path: str, force: bool = False, update_kubeconfig: bool = False
) -> None:
    """Clean up test clusters using component teardown hooks.

    Args:
        manifest_path: Path to the cluster manifest YAML.
        force: Continue teardown even if errors occur.
        update_kubeconfig: When ``True`` the ``kube-galaxy`` context is removed
            from ``$HOME/.kube/config`` without prompting the user.  When
            ``False`` (default) the user is asked interactively (if stdin is a
            terminal).
    """
    teardown_cluster(manifest_path, force=force)
    _handle_kubeconfig_removal(update_kubeconfig)


def cleanup_all(manifest_path: str, force: bool = False, update_kubeconfig: bool = False) -> None:
    """Full cleanup: files and cluster teardown.

    Args:
        manifest_path: Path to the cluster manifest YAML.
        force: Continue teardown even if errors occur.
        update_kubeconfig: When ``True`` the ``kube-galaxy`` context is removed
            from ``$HOME/.kube/config`` without prompting.
    """
    info("")
    try:
        cleanup_clusters(manifest_path, force, update_kubeconfig=update_kubeconfig)
    finally:
        cleanup_files()


def _handle_kubeconfig_removal(update_kubeconfig: bool) -> None:
    """Optionally remove the kube-galaxy context from ~/.kube/config."""
    if not context_exists():
        return

    if update_kubeconfig:
        _remove_context()
    elif is_interactive():
        if typer.confirm(
            f"\nRemove '{KUBE_GALAXY_CONTEXT}' context from ~/.kube/config?",
            default=True,
        ):
            _remove_context()
        else:
            info(f"Skipped: '{KUBE_GALAXY_CONTEXT}' context left in ~/.kube/config")


def _remove_context() -> None:
    """Remove the kube-galaxy context and log the outcome."""
    remove_kube_galaxy_context()
    success(f"Removed '{KUBE_GALAXY_CONTEXT}' context from ~/.kube/config.")
