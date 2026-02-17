"""Cleanup command handler."""

from pathlib import Path

import typer

from kube_galaxy.pkg.utils.logging import error, info, section, success


def cleanup_files() -> None:
    """Clean up temporary files and test artifacts."""
    section("Cleaning Up Temporary Files")

    cleanup_paths = [
        "test-results",
        "spread-results",
        "debug-logs",
        "cleanup-logs",
        "issue-data",
        "test-cluster-config.yaml",
    ]

    for path_str in cleanup_paths:
        path = Path(path_str)
        try:
            if path.is_dir():
                import shutil

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

    success("File cleanup completed!")


def cleanup_clusters(manifest_path: str | None = None, force: bool = False) -> None:
    """Clean up test clusters using component teardown hooks."""
    if not manifest_path:
        section("No manifest provided, using fallback kubeadm reset")
        _fallback_kubeadm_reset(force)
        return

    from kube_galaxy.pkg.cluster.cluster import teardown_cluster
    from kube_galaxy.pkg.utils.errors import ClusterError

    try:
        teardown_cluster(manifest_path, force=force)
    except ClusterError as e:
        if not force:
            error(f"Failed to tear down cluster: {e}")
            raise typer.Exit(code=1) from e


def _fallback_kubeadm_reset(force: bool) -> None:
    """Fallback to kubeadm reset when no manifest is available."""
    import shutil
    import subprocess

    if not shutil.which("kubeadm"):
        info("kubeadm not found, skipping cluster cleanup")
        return

    try:
        info("Running kubeadm reset --force")
        subprocess.run(
            ["sudo", "kubeadm", "reset", "--force"],
            check=True,
        )
        success("Cluster cleanup completed!")
    except subprocess.CalledProcessError as e:
        if force:
            error(f"kubeadm reset failed (continuing due to --force): {e}")
        else:
            error(f"Failed to clean up cluster: {e}")
            raise typer.Exit(code=1) from e


def cleanup_all(manifest_path: str | None = None, force: bool = False) -> None:
    """Full cleanup: files and cluster teardown."""
    cleanup_files()
    info("")
    cleanup_clusters(manifest_path, force)
