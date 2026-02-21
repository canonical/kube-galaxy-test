"""Cluster setup and provisioning with 8-stage component lifecycle."""

from pathlib import Path

from kube_galaxy.pkg.arch.detector import get_arch_info
from kube_galaxy.pkg.components import ComponentBase, find_component
from kube_galaxy.pkg.literals import Commands
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import ComponentConfig
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.gh import gh_output
from kube_galaxy.pkg.utils.logging import exception, info, section, success
from kube_galaxy.pkg.utils.shell import run

__all__ = ["setup_cluster", "teardown_cluster"]
SETUP_HOOKS = [
    "download",
    "pre_install",
    "install",
    "configure",
    "bootstrap",
    "verify",
]
TEARDOWN_HOOKS = [
    "stop",
    "delete",
    "post_delete",
]


def setup_cluster(manifest_path: str, work_dir: str = ".", debug: bool = False) -> None:
    """
    Set up a Kubernetes cluster using 6-stage component lifecycle.

    Args:
        manifest_path: Path to cluster manifest YAML
        work_dir: Working directory for artifacts
        debug: Enable debug output

    Raises:
        ClusterError: If cluster setup fails
    """
    try:
        # Load and validate manifest
        manifest = load_manifest(manifest_path)
        work_dir_path = Path(work_dir)

        section("Kubernetes Cluster Setup")
        info(f"Manifest: {manifest_path}")
        info(f"Work Dir: {work_dir}")
        info(f"Debug: {debug}")

        # Display configuration
        section("Configuration")
        info(f"Cluster Name: {manifest.name}")
        info(f"Kubernetes Version: {manifest.kubernetes_version}")
        info(f"Control Plane Nodes: {manifest.nodes.control_plane}")
        info(f"Worker Nodes: {manifest.nodes.worker}")

        # Detect architecture
        arch_info = get_arch_info()
        info(f"System Architecture: {arch_info.system}")
        info(f"Kubernetes Architecture: {arch_info.k8s}")
        info(f"Image Architecture: {arch_info.image}")

        # Create working directories
        work_dir_path.mkdir(parents=True, exist_ok=True)
        (work_dir_path / "components").mkdir(exist_ok=True)
        (work_dir_path / "logs").mkdir(exist_ok=True)

        # Get components in dependency order
        configs = manifest.components

        # Create all component instances
        instances: dict[str, ComponentBase] = {}
        for config in configs:
            component_class = find_component(config.name)
            instance = component_class(instances, manifest, config, arch_info)
            instances[config.name] = instance

        # Execute 6-stage lifecycle
        instances_list = list(instances.values())
        cluster_managers = sum(1 for inst in instances_list if inst.is_cluster_manager)
        if cluster_managers != 1:
            raise ClusterError(
                f"Manifest must have exactly 1 cluster manager component, found {cluster_managers}"
            )

        num_hooks = len(SETUP_HOOKS)
        for idx, hook_name in enumerate(SETUP_HOOKS):
            section(f"Stage {idx + 1}/{num_hooks}: {hook_name.capitalize()} Components")
            _run_hook(instances_list, configs, hook_name)

        section("Cluster Setup Complete!")
        success("Kubeconfig: $HOME/.kube/config")
        success(f"Cluster Name: {manifest.name}")
        success(f"Kubernetes Version: {manifest.kubernetes_version}")
        gh_output("CLUSTER_NAME", manifest.name)
        gh_output("KUBECONFIG", str(Path.home() / ".kube" / "config"))

    except Exception as exc:
        exception("Cluster setup failed", exc)
        raise ClusterError(f"Cluster setup failed: {exc}") from exc


def teardown_cluster(
    manifest_path: str, force: bool = False, work_dir: str = ".", debug: bool = False
) -> None:
    """
    Tear down a Kubernetes cluster using component teardown hooks.

    Args:
        manifest_path: Path to cluster manifest YAML
        force: Continue teardown even if errors occur
        work_dir: Working directory for artifacts
        debug: Enable debug output

    Raises:
        ClusterError: If cluster teardown fails (unless force=True)
    """
    try:
        # Load and validate manifest
        manifest = load_manifest(manifest_path)

        section("Kubernetes Cluster Teardown")
        info(f"Manifest: {manifest_path}")
        info(f"Work Dir: {work_dir}")
        info(f"Force: {force}")
        info(f"Debug: {debug}")

        # Display configuration
        section("Configuration")
        info(f"Cluster Name: {manifest.name}")
        info(f"Kubernetes Version: {manifest.kubernetes_version}")
        info(f"Control Plane Nodes: {manifest.nodes.control_plane}")
        info(f"Worker Nodes: {manifest.nodes.worker}")

        # Detect architecture
        arch_info = get_arch_info()
        info(f"System Architecture: {arch_info.system}")
        info(f"Kubernetes Architecture: {arch_info.k8s}")
        info(f"Image Architecture: {arch_info.image}")

        # Get components in dependency order, then reverse for teardown
        configs = list(reversed(manifest.components))

        # Create all component instances
        instances: dict[str, ComponentBase] = {}
        for config in configs:
            component_class = find_component(config.name)
            instance = component_class(instances, manifest, config)
            instances[config.name] = instance

        # Execute 3-stage teardown lifecycle in reverse dependency order
        instances_list = list(instances.values())
        num_hooks = len(TEARDOWN_HOOKS)
        for idx, hook_name in enumerate(TEARDOWN_HOOKS):
            section(f"Stage {idx + 1}/{num_hooks}: {hook_name.capitalize()} Components")
            _run_hook(instances_list, configs, hook_name, force)

        # Final cleanup: remove any remaining kube-galaxy alternatives
        _cleanup_kube_galaxy_alternatives(force)

        section("Cluster Teardown Complete!")
        success(f"Cluster '{manifest.name}' has been torn down")
        gh_output("CLUSTER_TEARDOWN_STATUS", "complete")

    except Exception as exc:
        if force:
            exception("Cluster teardown encountered errors (continuing due to --force)", exc)
            success("Cluster teardown completed with errors (forced)")
        else:
            exception("Cluster teardown failed", exc)
            raise ClusterError(f"Cluster teardown failed: {exc}") from exc


def _run_hook(
    instances: list[ComponentBase],
    configs: list[ComponentConfig],
    hook_name: str,
    force: bool = False,
) -> None:
    """
    Run a specific lifecycle hook for all components.

    Args:
        instances: List of component instances
        configs: List of component configs (must be in same order as instances)
        hook_name: Name of the hook to run (e.g., "install")
        force: Continue execution even if errors occur

    Raises:
        ClusterError: If any component hook fails
    """
    hook_name_caps = hook_name.title()
    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: {hook_name_caps}...")
        hook_method = getattr(instance, f"{hook_name}_hook", None)
        if not hook_method:
            raise ClusterError(f"{hook_name_caps} hook not implemented for {config.name}")
        try:
            hook_method()
        except Exception as exc:
            forced = " (continuing due to --force)" if force else ""
            message = f"{hook_name_caps} failed for {config.name}{forced}: {exc}"
            exception(f"  ✗ {message}", exc)
            if not force:
                raise ClusterError(message) from exc


def _cleanup_kube_galaxy_alternatives(force: bool) -> None:
    """
    Clean up any remaining kube-galaxy alternatives in /opt/kube-galaxy.

    This function scans for any remaining component directories and removes
    their alternatives as a final safety net.

    Args:
        force: Continue cleanup even if errors occur
    """
    kube_galaxy_dir = Path("/opt/kube-galaxy")
    if not kube_galaxy_dir.exists():
        return

    info("  Final cleanup: removing remaining alternatives...")
    for binary in kube_galaxy_dir.glob("**/bin/*"):
        if binary.is_file():
            cmd = [*Commands.UPDATE_ALTERNATIVES_REMOVE, binary.name, str(binary)]
            run(cmd, check=False)

    # Remove the entire /opt/kube-galaxy directory
    try:
        run([*Commands.SUDO_RM_RF, str(kube_galaxy_dir)], check=False)
        info(f"  Removed {kube_galaxy_dir}")
    except Exception as e:
        if force:
            info(f"  Warning: Failed to remove {kube_galaxy_dir}: {e}")
        else:
            raise
