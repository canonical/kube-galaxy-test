"""
Base class for component installation and lifecycle management.

All component implementations should inherit from ComponentBase and
override the lifecycle hooks they need.
"""

import shutil
from abc import abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import LiteralString, cast

from kube_galaxy.pkg.arch.detector import ArchInfo
from kube_galaxy.pkg.components.strategies import (
    _INSTALL_STRATEGIES,
    _TEST_STRATEGIES,
    _InstallStrategy,
    _TestStrategy,
)
from kube_galaxy.pkg.literals import Permissions, SystemPaths, Timeouts
from kube_galaxy.pkg.manifest.models import ComponentConfig, InstallMethod, Manifest, NodeRole
from kube_galaxy.pkg.units._base import Unit
from kube_galaxy.pkg.units.local import LocalUnit
from kube_galaxy.pkg.utils.components import install_binary, remove_binary
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.paths import ensure_dir


class ComponentBase:
    """
    Base class for Kubernetes component installation.

    Each component should subclass this and override the lifecycle hooks
    it needs. The component has access to:
    - The full manifest (self.manifest)
    - Its own component configuration (self.config)
    - Architecture information (self.arch_info)
    - The unit it runs on (self.unit)

    Lifecycle hooks (all have default empty implementations):
    Setup Hooks:
    1. download_hook() - Download artifacts
    2. pre_install_hook() - Prepare machine for installation
    3. install_hook() - Install the component
    4. configure_hook() - Configure component (config files, settings)
    5. bootstrap_hook() - Initialize/start the component
    6. verify_hook() - Verify component is working

    Teardown Hooks (run in reverse dependency order):
    7. stop_hook() - Stop services and processes
    8. delete_hook() - Remove binaries and configurations
    9. post_delete_hook() - Clean up remaining files, images, etc.

    Each hook can be overridden. If not overridden, the default (empty)
    implementation is used and effectively skips that stage.

    Use regular component attributes for state management between hooks.
    """

    # Timeout configuration (in seconds) - override in subclass
    BOOTSTRAP_TIMEOUT = Timeouts.BOOTSTRAP_TIMEOUT

    # Component metadata - override in subclass
    LOCAL_REGISTRY: LiteralString = "registry.k8s.io"

    unit: Unit = LocalUnit()

    def __init__(
        self,
        components: dict[str, "ComponentBase"],
        manifest: Manifest,
        config: ComponentConfig,
        arch_info: ArchInfo,
    ) -> None:
        """
        Initialize component with components, manifest, config, and unit.

        Args:
            components: Dict of all components
            manifest: The full Manifest object
            config: The ComponentConfig object for this specific component
            arch_info: Architecture information
        """
        self.components = components
        self.manifest = manifest
        self.config = config
        # Allow tests and callers to omit arch_info; default to detected arch
        self.arch_info = arch_info
        # for InstallMethod Binary or BinaryArchive
        self.binary_path: Path | None = None  # path to downloaded binary (before installation)
        self.install_path: str | None = None  # path to root installed bin
        # for InstallMethod Image or ImageArchive
        self.image_repository: str | None = None
        self.image_tag: str | None = None
        # for InstallMethod ContainerManifest
        self.manifest_path: Path | None = None  # path to downloaded manifest file

        install_method = config.installation.method
        if install_method not in _INSTALL_STRATEGIES:
            raise ComponentError(f"Unsupported installation method: {install_method}")
        self._install_strategy: _InstallStrategy = _INSTALL_STRATEGIES[install_method]

        test_method = config.test.method
        if test_method not in _TEST_STRATEGIES:
            raise ComponentError(f"Unsupported test method: {test_method}")
        self._test_strategy: _TestStrategy = _TEST_STRATEGIES[test_method]

    @property
    def name(self) -> str:
        """
        Get the component's name.

        Returns:
            Component name from config
        """
        return self.config.name

    @property
    def is_cluster_manager(self) -> bool:
        """
        Check if this component is a cluster manager.

        Returns:
            True if this component is responsible for cluster lifecycle management (e.g., kubeadm)
        """
        return isinstance(self, ClusterComponentBase)

    def get_cluster_manager(self) -> "ClusterComponentBase":
        """
        Get the cluster manager component.

        Returns:
            The instance of the cluster manager component

        Raises:
            ComponentError: If no cluster manager is found in components
        """
        for component in self.components.values():
            if component.is_cluster_manager:
                return cast("ClusterComponentBase", component)
        raise ComponentError("No cluster manager component found in components")

    # Lifecycle hooks - all have default empty implementations
    # Override in subclass as needed
    def run_hook(self, hook_name: str) -> None:
        hook_name_caps = hook_name.title()
        hook_method = getattr(self, f"{hook_name}_hook", None)
        if not hook_method:
            raise ComponentError(f"{hook_name_caps} hook not implemented for {self.name}")
        hook_method()

    def download_hook(self) -> None:
        """
        Download component artifacts.

        This hook runs in the DOWNLOAD stage (can be parallelized).
        Override to implement download logic.

        Access component config via self.config (repo, release, installation).
        """
        self._install_strategy.download(self)
        self._test_strategy.download(self)

    def pre_install_hook(self) -> None:
        """
        Prepare machine for component installation.

        This hook runs in the PRE_INSTALL stage (sequential).
        Override to implement machine preparation (swapoff, sysctl, etc.).
        """
        self._install_strategy.pre_install(self)
        self._test_strategy.pre_install(self)

    def install_hook(self) -> None:
        """
        Install the component.

        This hook runs in the INSTALL stage (sequential,
        dependency-ordered). Override to implement installation logic.

        Access component config via self.config (repo, release, installation).
        """
        self._install_strategy.install(self)
        self._test_strategy.install(self)

    def bootstrap_hook(self) -> None:
        """
        Initialize and start the component.

        This hook runs in the BOOTSTRAP stage (sequential, dependency-ordered).
        Override to implement service startup logic.
        """

        self._install_strategy.bootstrap(self)
        self._test_strategy.bootstrap(self)

    def configure_hook(self) -> None:
        """
        Configure the component (create config files, etc.).

        This hook runs in the CONFIGURE stage before BOOTSTRAP (sequential).
        Override to implement configuration logic.
        """
        self._install_strategy.configure(self)
        self._test_strategy.configure(self)

    def verify_hook(self) -> None:
        """
        Verify the component is working correctly.

        This hook runs in the VERIFY stage (sequential).
        Override to implement health check logic.
        """
        self._install_strategy.verify(self)
        self._test_strategy.verify(self)

    def remove_hook(self) -> None:
        """
        Remove/uninstall the component.

        This hook runs during component removal.
        Override to implement cleanup logic.
        """
        self._install_strategy.remove(self)
        self._test_strategy.remove(self)

    # Component directory and alternatives management methods
    @property
    def component_dir(self) -> Path:
        """
        Get the component's installation directory.

        Returns:
            Path to /opt/kube-galaxy/{self.name}/
        """
        return SystemPaths.component_dir(self.name)

    @property
    def component_tmp_dir(self) -> Path:
        """
        Get the component's local staging directory on the orchestrator.

        Lives at ``cwd()/tmp/opt/kube-galaxy/{name}/temp`` — user-writable and
        consistent across kube-galaxy invocations.  It mirrors the component's
        temp directory on the unit (``/opt/kube-galaxy/{name}/temp``); the unit
        path is derived by stripping the ``cwd()/tmp`` staging-root prefix.

        Returns:
            Path to cwd()/tmp/opt/kube-galaxy/{self.name}/temp
        """
        return SystemPaths.local_component_temp_dir(self.name)

    @property
    def extracted_dir(self) -> Path | None:
        """Get the extracted directory for this component."""
        if self.config.installation.method not in (
            InstallMethod.BINARY_ARCHIVE,
            InstallMethod.CONTAINER_IMAGE_ARCHIVE,
        ):
            return None
        return self.component_tmp_dir / "extracted"

    def remove_component_alternatives(self) -> None:
        """
        Remove all alternatives for binaries in this component's bin directory.
        """
        component_bin_dir = SystemPaths.component_bin_dir(self.name)
        result = self.unit.run(["ls", str(component_bin_dir)], privileged=True, check=False)
        if result.returncode == 0:
            for binary_name in result.stdout.split():
                binary_path = component_bin_dir / binary_name
                remove_binary(binary_path, self.unit)

    def cleanup_component_dir(self) -> None:
        """
        Remove the entire component directory on the unit.
        """
        self.unit.run(["rm", "-rf", str(self.component_dir)], privileged=True, check=False)

    # Teardown hooks - all have default empty implementations
    # Override in subclass as needed

    def stop_hook(self) -> None:
        """
        Stop component services and processes.

        This hook runs in the STOP stage of teardown (sequential, reverse dependency order).
        Override to implement service shutdown logic.
        """
        pass

    def delete_hook(self) -> None:
        """
        Delete component binaries and configuration files.

        This hook runs in the DELETE stage of teardown (sequential, reverse dependency order).
        Override to implement binary/config removal logic.
        """
        # Remove update-alternatives entries for this component
        self.remove_component_alternatives()

        # extracted_dir is a local staging directory — clean it up locally
        if self.extracted_dir and self.extracted_dir.exists():
            shutil.rmtree(self.extracted_dir, ignore_errors=True)

        # Remove component directory (binaries) on the unit
        self.cleanup_component_dir()

    def post_delete_hook(self) -> None:
        """
        Clean up remaining files, images, and artifacts.

        This hook runs in the POST_DELETE stage of teardown (sequential, reverse dependency order).
        Override to implement final cleanup logic.
        """
        pass

    # Common utility methods - reduces code duplication across components

    def ensure_temp_dir(self) -> Path:
        """
        Ensure the component local staging directory exists and return its path.

        Creates ``cwd()/tmp/opt/kube-galaxy/<name>/temp`` on the orchestrator.
        This directory is user-writable and requires no root access.  It is
        used to stage files (downloads, generated configs) before they are
        pushed to the unit via ``unit.put()``.

        Unit-side directories are **not** created here — each operation that
        writes to the unit (``install_binary``, ``create_systemd_service``,
        ``write_config_file``, …) creates the necessary remote directories
        immediately before pushing, so this method is safe to call during the
        DOWNLOAD hook when the unit agent may not yet be running.

        Returns:
            Path to the local staging directory (``component_tmp_dir``).
        """
        staging_dir = self.component_tmp_dir
        ensure_dir(staging_dir)
        return staging_dir

    def install_downloaded_binary(self, binary_path: Path, binary_name: str | None = None) -> str:
        """
        Install downloaded binary using standard install_binary function.

        Args:
            binary_path: Path to binary file
            binary_name: Binary name (defaults to component name)

        Returns:
            Installation path

        Raises:
            ComponentError: If installation fails
        """
        if not binary_path.exists():
            raise ComponentError(f"{self.name} binary not found at {binary_path}")

        name = binary_name or self.name
        return install_binary(binary_path, name, self.name, self.unit)

    def create_systemd_service(
        self,
        service_name: str,
        service_content: str,
        system_location: bool = True,
        enabled: bool = False,
    ) -> None:
        """
        Create a systemd service file.

        Args:
            service_name: Name of the service
            service_content: Service file content
            system_location: If True, use /etc/systemd/system; else /usr/lib/systemd/system

        Raises:
            ComponentError: If service file creation fails
        """
        try:
            # Write content to a local staging file (user-writable)
            staging_dir = self.ensure_temp_dir()
            local_file = staging_dir / f"{service_name}.service"
            local_file.write_text(service_content)

            # Create target directory on unit, push file, then reload
            target_dir = "/etc/systemd/system" if system_location else "/usr/lib/systemd/system"
            target_path = f"{target_dir}/{service_name}.service"
            self.unit.run(["mkdir", "-p", target_dir], privileged=True)
            self.unit.put(local_file, target_path)

            # Reload systemd and enable service
            self.unit.run(["systemctl", "daemon-reload"], privileged=True)
            if enabled:
                self.unit.run(["systemctl", "enable", service_name], privileged=True)
        except Exception as e:
            raise ComponentError(f"Failed to create {service_name} service: {e}") from e

    def write_config_file(
        self, config_content: str, target_path: str | Path, mode: str = Permissions.READABLE
    ) -> None:
        """
        Write configuration content to a file via temporary file.

        Args:
            config_content: Configuration file content
            target_path: Final path for config file on the unit
            mode: File permissions (default: 644)

        Raises:
            ComponentError: If file writing fails
        """
        try:
            staging_dir = self.ensure_temp_dir()
            local_file = staging_dir / "config"
            local_file.write_text(config_content)

            # Create parent directory on unit, push file, set permissions
            self.unit.run(["mkdir", "-p", str(Path(target_path).parent)], privileged=True)
            self.unit.put(local_file, str(target_path))
            self.unit.run(["chmod", mode, str(target_path)], privileged=True)
        except Exception as e:
            raise ComponentError(f"Failed to write config to {target_path}: {e}") from e

    def remove_directories(
        self, directories: Iterable[str | Path], component_name: str | None = None
    ) -> None:
        """
        Remove multiple directories (best effort).

        Args:
            directories: List of directory paths to remove
            component_name: Component name for logging (defaults to self.name)
        """
        name = component_name or self.name
        for directory in directories:
            dir_path = Path(directory)
            if dir_path.exists():
                try:
                    self.unit.run(["rm", "-rf", str(dir_path)], privileged=True, check=False)
                    info(f"Removed {name} directory: {dir_path}")
                except Exception as e:
                    info(f"Failed to remove {dir_path}: {e}")

    def remove_config_files(
        self, config_files: Iterable[str | Path], component_name: str | None = None
    ) -> None:
        """
        Remove multiple configuration files (best effort).

        Args:
            config_files: List of config file paths to remove
            component_name: Component name for logging (defaults to self.name)
        """
        name = component_name or self.name
        for config_path in config_files:
            try:
                self.unit.run(["rm", "-rf", str(config_path)], privileged=True, check=False)
                info(f"Removed {name} config: {config_path}")
            except Exception as e:
                info(f"Failed to remove {config_path}: {e}")

    def remove_installed_binary(self) -> None:
        """
        Remove the installed binary if it exists.
        """
        if self.install_path:
            self.unit.run(["rm", "-f", self.install_path], privileged=True, check=False)
            info(f"Removed {self.name} binary: {self.install_path}")


class ClusterComponentBase(ComponentBase):
    """
    Base class for cluster lifecycle managers (kubeadm, k3s, rke2, …).

    The Orchestrator coordinates multi-node join via this interface — never by
    knowing the concrete class.  ``KubeadmComponent`` implements all four methods.
    A future k3s component implements the same interface with a different token format.
    """

    @abstractmethod
    def init_cluster(self) -> None:
        """Bootstrap the initial control-plane on this unit."""

    @abstractmethod
    def generate_join_token(self, role: NodeRole) -> str:
        """Called on the control-plane unit.  Returns a single-use token for the
        joining unit.  Role distinguishes HA control-plane joins from worker joins.
        """

    @abstractmethod
    def join_cluster(self, token: str, role: NodeRole) -> None:
        """Called on the joining unit.  Consumes the token from generate_join_token()."""

    @abstractmethod
    def pull_kubeconfig(self) -> None:
        """Pull kubeconfig from this unit to the orchestrator's ~/.kube/config."""

    def find_image_retag(self, image: str) -> str:
        """
        Find the retagged image name for a given image.

        Args:
            image: Original image name

        Returns:
            Retagged image name
        """
        return ""
