"""Cluster setup and provisioning with 8-stage component lifecycle."""

from pathlib import Path

from kube_galaxy.pkg.arch.detector import ArchInfo, get_arch_info
from kube_galaxy.pkg.components import COMPONENTS, ComponentBase
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import ComponentConfig
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.gh import gh_output
from kube_galaxy.pkg.utils.logging import exception, info, section, success


def setup_cluster(manifest_path: str, work_dir: str = ".", debug: bool = False) -> None:
    """
    Set up a Kubernetes cluster using 8-stage component lifecycle.

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
        configs = manifest.get_components_by_priority()

        # Create all component instances
        instances: dict[str, ComponentBase] = {}
        for config in configs:
            component_class = COMPONENTS.get(config.name, ComponentBase)
            instance = component_class(instances, manifest, config)
            instances[config.name] = instance

        # Execute 8-stage lifecycle
        instances_list = list(instances.values())
        _download_components(instances_list, configs, arch_info)
        _pre_install_components(instances_list, configs)
        _install_components(instances_list, configs, arch_info)
        _configure_components(instances_list, configs)
        _bootstrap_components(instances_list, configs)
        _post_bootstrap_components(instances_list, configs)
        _verify_components(instances_list, configs)
        _test_components(instances_list, configs)

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
        configs = list(reversed(manifest.get_components_by_priority()))

        # Create all component instances
        instances: dict[str, ComponentBase] = {}
        for config in configs:
            component_class = COMPONENTS.get(config.name, ComponentBase)
            instance = component_class(instances, manifest, config)
            instances[config.name] = instance

        # Execute 3-stage teardown lifecycle in reverse dependency order
        instances_list = list(instances.values())
        _stop_components(instances_list, configs, force)
        _delete_components(instances_list, configs, force)
        _post_delete_components(instances_list, configs, force)

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


def _download_components(
    instances: list[ComponentBase], configs: list[ComponentConfig], arch_info: ArchInfo
) -> None:
    """Stage 1/8: Download all component artifacts."""
    section("Stage 1/8: Downloading Components")

    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: downloading...")
        try:
            instance.download_hook(arch_info.k8s)
        except Exception as exc:
            exception(f"  ✗ Download failed for {config.name}", exc)
            raise


def _pre_install_components(instances: list[ComponentBase], configs: list[ComponentConfig]) -> None:
    """Stage 2/8: Pre-installation machine preparation."""
    section("Stage 2/8: Pre-installation Setup")

    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: preparing...")
        try:
            instance.pre_install_hook()
        except Exception as exc:
            exception(f"  ✗ Pre-install failed for {config.name}", exc)
            raise


def _install_components(
    instances: list[ComponentBase], configs: list[ComponentConfig], arch_info: ArchInfo
) -> None:
    """Stage 3/8: Install component binaries/configs."""
    section("Stage 3/8: Installing Components")

    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: installing...")
        try:
            instance.install_hook(arch_info.k8s)
        except Exception as exc:
            exception(f"  ✗ Install failed for {config.name}", exc)
            raise


def _configure_components(instances: list[ComponentBase], configs: list[ComponentConfig]) -> None:
    """Stage 4/8: Configure components (config files, settings)."""
    section("Stage 4/8: Configuring Components")

    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: configuring...")
        try:
            instance.configure_hook()
        except Exception as exc:
            exception(f"  ✗ Configure failed for {config.name}", exc)
            raise


def _bootstrap_components(instances: list[ComponentBase], configs: list[ComponentConfig]) -> None:
    """Stage 5/8: Bootstrap/start services (systemd start, kubeadm init)."""
    section("Stage 5/8: Bootstrapping Services")

    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: bootstrapping...")
        try:
            instance.bootstrap_hook()
        except Exception as exc:
            exception(f"  ✗ Bootstrap failed for {config.name}", exc)
            raise


def _post_bootstrap_components(
    instances: list[ComponentBase], configs: list[ComponentConfig]
) -> None:
    """Stage 6/8: Post-bootstrap tasks (kubeconfig setup, etc.)."""
    section("Stage 6/8: Post-bootstrap Tasks")

    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: post-bootstrap...")
        try:
            instance.post_bootstrap_hook()
        except Exception as exc:
            exception(f"  ✗ Post-bootstrap failed for {config.name}", exc)
            raise


def _verify_components(instances: list[ComponentBase], configs: list[ComponentConfig]) -> None:
    """Stage 7/8: Verify components are working."""
    section("Stage 7/8: Verifying Components")

    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: verifying...")
        try:
            instance.verify_hook()
        except Exception as exc:
            exception(f"  ✗ Verification failed for {config.name}", exc)
            raise


def _test_components(instances: list[ComponentBase], configs: list[ComponentConfig]) -> None:
    """Stage 8/8: Run component tests (optional)."""
    section("Stage 8/8: Testing Components")

    for config, instance in zip(configs, instances, strict=True):
        if config.use_spread:
            info(f"  {config.name}: running tests...")
            try:
                instance.test_hook()
            except Exception as exc:
                exception(f"  ✗ Tests failed for {config.name}", exc)
                raise
        else:
            info(f"  {config.name}: skipping tests (use_spread=false)")


def _stop_components(
    instances: list[ComponentBase], configs: list[ComponentConfig], force: bool
) -> None:
    """Teardown Stage 1/3: Stop component services."""
    section("Teardown Stage 1/3: Stopping Components")

    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: stopping...")
        try:
            instance.stop_hook()
        except Exception as exc:
            if force:
                exception(f"  ✗ Stop failed for {config.name} (continuing due to --force)", exc)
            else:
                exception(f"  ✗ Stop failed for {config.name}", exc)
                raise


def _delete_components(
    instances: list[ComponentBase], configs: list[ComponentConfig], force: bool
) -> None:
    """Teardown Stage 2/3: Delete component binaries and configs."""
    section("Teardown Stage 2/3: Deleting Components")

    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: deleting...")
        try:
            instance.delete_hook()
        except Exception as exc:
            if force:
                exception(f"  ✗ Delete failed for {config.name} (continuing due to --force)", exc)
            else:
                exception(f"  ✗ Delete failed for {config.name}", exc)
                raise


def _post_delete_components(
    instances: list[ComponentBase], configs: list[ComponentConfig], force: bool
) -> None:
    """Teardown Stage 3/3: Clean up remaining artifacts."""
    section("Teardown Stage 3/3: Post-Delete Cleanup")

    for config, instance in zip(configs, instances, strict=True):
        info(f"  {config.name}: cleaning up...")
        try:
            instance.post_delete_hook()
        except Exception as exc:
            if force:
                exception(
                    f"  ✗ Post-delete failed for {config.name} (continuing due to --force)", exc
                )
            else:
                exception(f"  ✗ Post-delete failed for {config.name}", exc)
                raise
