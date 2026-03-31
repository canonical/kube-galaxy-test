"""Cluster setup and provisioning with 8-stage component lifecycle."""

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from kube_galaxy.pkg.cluster_context import ClusterContext
from kube_galaxy.pkg.components import ComponentBase, find_component
from kube_galaxy.pkg.literals import Commands, Hooks, SetupHooks, TeardownHooks, TestDirectories
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import Manifest, NodeRole
from kube_galaxy.pkg.units import Unit
from kube_galaxy.pkg.units._base import UnitProvider
from kube_galaxy.pkg.units.provider import provider_factory
from kube_galaxy.pkg.utils.artifact_server import ArtifactServer
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.gh import gh_output
from kube_galaxy.pkg.utils.logging import exception, info, section, success
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.registry_mirror import RegistryMirror
from kube_galaxy.pkg.utils.shell import run

__all__ = ["setup_cluster", "teardown_cluster"]


def _log_cluster_info(task: str, manifest: Manifest, force: None | bool = None) -> None:
    """Log cluster configuration and detected architecture."""

    section(f"Kubernetes Cluster {task}")
    info(f"Manifest: {manifest.path}")
    if force is not None:
        info(f"Force: {force}")

    # Display configuration
    section("Configuration")
    info(f"Cluster Name: {manifest.name}")
    info(f"Kubernetes Version: {manifest.kubernetes_version}")


def setup_cluster(manifest_path: Path | str) -> None:
    """
    Set up a Kubernetes cluster using 6-stage component lifecycle.

    Args:
        manifest_path: Path to cluster manifest YAML
        work_dir: Working directory for artifacts

    Raises:
        ClusterError: If cluster setup fails
    """
    try:
        # Load and validate manifest
        manifest = load_manifest(manifest_path)

        _log_cluster_info("Setup", manifest)

        # Create working directories
        ensure_dir(Path() / TestDirectories.DEBUG_LOGS)

        # Get components in dependency order
        configs = manifest.components

        # Provision the orchestrator unit via the manifest's provider
        provider = provider_factory(manifest)
        units = provider.provision_all()
        info("Waiting for Units to become ready...")
        for unit in units:
            unit.enlist()

        lead_unit = provider.locate(NodeRole.CONTROL_PLANE, 0)
        info(f"Lead Control-Plane unit '{lead_unit.name}' is ready")

        # Create all component resources
        ctx = ClusterContext(components={})
        ctx.units = units
        for config in configs:
            component_class = find_component(config.name)
            resource = component_class(ctx, manifest, config, lead_unit.arch)
            ctx.components[config.name] = resource

        # Execute 6-stage lifecycle
        cluster_managers = sum(1 for res in ctx.components.values() if res.is_cluster_manager)
        if cluster_managers != 1:
            raise ClusterError(
                f"Manifest must have exactly 1 cluster manager component, found {cluster_managers}"
            )

        # Start the registry mirror (if enabled) — it remains running until
        # teardown_cluster stops it, so cluster nodes can pull images at any time.
        reg_cfg = manifest.artifact.registry
        if reg_cfg.enabled:
            mirror = RegistryMirror(reg_cfg)
            mirror.start()
            ctx.registry_mirror = mirror

        # DOWNLOAD phase runs before the artifact server so artifacts are
        # present on disk when the server starts.
        section(f"Stage 1/{len(SetupHooks)}: Download Components")
        _run_hook(lead_unit, ctx, SetupHooks.DOWNLOAD)

        # Start the artifact server so nodes can pull binaries without
        # the orchestrator pushing files directly onto them.
        with ArtifactServer() as artifact_server:
            info(f"Artifact server started at {artifact_server.base_url}")
            ctx.artifact_server = artifact_server

            remaining_hooks = [h for h in SetupHooks if h != SetupHooks.DOWNLOAD]
            for idx, hook in enumerate(remaining_hooks, 2):
                section(f"Stage {idx}/{len(SetupHooks)}: {hook.value.capitalize()} Components")
                for unit in units:
                    _run_hook(unit, ctx, hook)
        ctx.artifact_server = None

        section("Cluster Setup Complete!")
        success("Kubeconfig: /opt/kube-galaxy/kubeconfig")
        gh_output("CLUSTER_NAME", manifest.name)
        gh_output("KUBECONFIG", str(Path.home() / ".kube" / "config"))

    except Exception as exc:
        exception("Cluster setup failed", exc)
        raise ClusterError(f"Cluster setup failed: {exc}") from exc


def teardown_cluster(manifest_path: str, force: bool = False) -> None:
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

        _log_cluster_info("Teardown", manifest, force)

        # Get components in dependency order, then reverse for teardown
        configs = list(reversed(manifest.components))

        # Locate the orchestrator unit via the manifest's provider (no new provisioning)
        provider = provider_factory(manifest)
        units = list(reversed(provider.locate_all()))

        # Create all component resources
        ctx = ClusterContext(components={})
        ctx.units = units
        for config in configs:
            for unit in units:
                component_class = find_component(config.name)
                resource = component_class(ctx, manifest, config, unit.arch)
                ctx.components[config.name] = resource

        # Execute 3-stage teardown lifecycle in reverse dependency order
        num_hooks = len(TeardownHooks)
        for idx, hook in enumerate(TeardownHooks):
            section(f"Stage {idx + 1}/{num_hooks}: {hook.value.capitalize()} Components")
            for unit in units:
                _run_hook(unit, ctx, hook, force)

        # Stop the registry mirror now that all component hooks are done.
        reg_cfg = manifest.artifact.registry
        if reg_cfg.enabled:
            RegistryMirror(reg_cfg).stop(force)

        # Deprovision all nodes (no-op for non-ephemeral providers)
        _deprovision(provider, force)

        # Final cleanup: remove any remaining kube-galaxy alternatives
        _cleanup_kube_galaxy_alternatives(force)

        section("Cluster Teardown Complete!")
        success(f"Cluster '{manifest.name}' is torn down")
        gh_output("CLUSTER_TEARDOWN_STATUS", "complete")

    except Exception as exc:
        if force:
            exception("Cluster teardown encountered errors (continuing due to --force)", exc)
            success("Cluster teardown completed with errors (forced)")
        else:
            exception("Cluster teardown failed", exc)
            raise ClusterError(f"Cluster teardown failed: {exc}") from exc


@contextmanager
def _attach_unit(components: list[ComponentBase], unit: Unit) -> Generator[None, None, None]:
    """Attach the given unit to all components that require it."""
    restored = []
    for component in components:
        component.unit, restore = unit, component.unit
        restored.append(restore)
    yield
    for component, restore in zip(components, restored, strict=True):
        component.unit = restore


def _run_hook(unit: Unit, ctx: ClusterContext, hook: Hooks, force: bool = False) -> None:
    """
    Run a specific lifecycle hook for all components.

    Args:
        ctx: Shared cluster context; components iterated in insertion order
        hook: The hook to run (e.g., SetupHooks.INSTALL)
        force: Continue execution even if errors occur

    Raises:
        ClusterError: If any component hook fails
    """
    hook_name_caps = hook.value.title()
    max_workers = 10 if hook.is_parallel else 1
    components = list(ctx.components.values())
    unit.set_cluster_context(ctx)
    with _attach_unit(components, unit), ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures_list = []

        # Submit all tasks in component order
        for name, resource in ctx.components.items():
            future = executor.submit(resource.run_hook, hook.value)
            futures_list.append((name, future))

        # Collect results in submission order
        for component_name, future in futures_list:
            try:
                future.result()
            except Exception as exc:
                forced = " (continuing due to --force)" if force else ""
                message = f"{hook_name_caps} failed for {component_name}{forced}: {exc}"
                exception(f"  ✗ {message}", exc)
                if not force:
                    raise ClusterError(message) from exc


def _deprovision(provider: UnitProvider, force: bool) -> None:
    """Deprovision all units managed by the provider.

    For ephemeral providers (LXD, Multipass) this destroys the VMs.
    For non-ephemeral providers (local, SSH) this is a no-op.

    Args:
        provider: The active UnitProvider.
        force: Continue even if deprovisioning encounters errors.
    """
    if not provider.is_ephemeral:
        return
    info("  Deprovisioning cluster nodes...")
    try:
        provider.deprovision_all()
        info("  All nodes deprovisioned")
    except Exception as exc:
        if force:
            exception("  Warning: deprovisioning encountered errors (continuing)", exc)
        else:
            raise


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
