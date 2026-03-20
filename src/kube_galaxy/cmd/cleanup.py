"""Cleanup command handler."""

import shutil
from pathlib import Path

from kube_galaxy.pkg.cluster import teardown_cluster
from kube_galaxy.pkg.literals import FilePatterns, SystemPaths, TestDirectories
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

    # Remove the active-manifest symlink so subsequent commands require an explicit manifest
    active_link = SystemPaths.active_manifest_link()
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


def cleanup_clusters(manifest_path: str, force: bool = False) -> None:
    """Clean up test clusters using component teardown hooks."""
    teardown_cluster(manifest_path, force=force)


def cleanup_all(manifest_path: str, force: bool = False) -> None:
    """Full cleanup: files and cluster teardown."""
    cleanup_files()
    info("")
    cleanup_clusters(manifest_path, force)
