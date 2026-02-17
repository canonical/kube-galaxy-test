"""
Base class for component installation and lifecycle management.

All component implementations should inherit from ComponentBase and
override the lifecycle hooks they need.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from kube_galaxy.pkg.components._constants import (
    DEFAULT_BOOTSTRAP_TIMEOUT,
    DEFAULT_CONFIGURE_TIMEOUT,
    DEFAULT_DOWNLOAD_TIMEOUT,
    DEFAULT_INSTALL_TIMEOUT,
    DEFAULT_POST_BOOTSTRAP_TIMEOUT,
    DEFAULT_PRE_INSTALL_TIMEOUT,
    DEFAULT_TEST_TIMEOUT,
    DEFAULT_VERIFY_TIMEOUT,
)
from kube_galaxy.pkg.literals import Commands, Permissions, SystemPaths
from kube_galaxy.pkg.manifest.models import ComponentConfig, InstallMethod, Manifest
from kube_galaxy.pkg.utils.components import download_file, extract_archive, install_binary
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.shell import run


class ComponentBase:
    """
    Base class for Kubernetes component installation.

    Each component should subclass this and override the lifecycle hooks
    it needs. The component has access to:
    - The full manifest (self.manifest)
    - Its own component configuration (self.config)
    - Architecture information (passed to hooks)

    Lifecycle hooks (all have default empty implementations):
    Setup Hooks:
    1. download_hook(repo, release, method, source_format, arch) - Download artifacts
    2. pre_install_hook() - Prepare machine for installation
    3. install_hook(repo, release, method, source_format, arch) - Install the component
    4. configure_hook() - Configure component (config files, settings)
    5. bootstrap_hook() - Initialize/start the component
    6. post_bootstrap_hook() - Post-initialization tasks
    7. verify_hook() - Verify component is working
    8. test_hook() - Run component tests (optional)

    Teardown Hooks (run in reverse dependency order):
    9. stop_hook() - Stop services and processes
    10. delete_hook() - Remove binaries and configurations
    11. post_delete_hook() - Clean up remaining files, images, etc.

    Each hook can be overridden. If not overridden, the default (empty)
    implementation is used and effectively skips that stage.

    Use regular instance attributes for state management between hooks.
    """

    # Timeout configuration (in seconds) - override in subclass
    DOWNLOAD_TIMEOUT = DEFAULT_DOWNLOAD_TIMEOUT
    PRE_INSTALL_TIMEOUT = DEFAULT_PRE_INSTALL_TIMEOUT
    INSTALL_TIMEOUT = DEFAULT_INSTALL_TIMEOUT
    CONFIGURE_TIMEOUT = DEFAULT_CONFIGURE_TIMEOUT
    BOOTSTRAP_TIMEOUT = DEFAULT_BOOTSTRAP_TIMEOUT
    POST_BOOTSTRAP_TIMEOUT = DEFAULT_POST_BOOTSTRAP_TIMEOUT
    VERIFY_TIMEOUT = DEFAULT_VERIFY_TIMEOUT
    TEST_TIMEOUT = DEFAULT_TEST_TIMEOUT

    # Component metadata - override in subclass
    CATEGORY: str = ""
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY: int = 50

    def __init__(
        self,
        instances: dict[str, "ComponentBase"],
        manifest: Manifest,
        config: ComponentConfig,
    ) -> None:
        """
        Initialize component with instances, manifest, and config.

        Args:
            instances: Dict of all component instances (growing as components are created)
            manifest: The full Manifest object
            config: The ComponentConfig object for this specific component
        """
        self.instances = instances
        self.manifest = manifest
        self.config = config
        self.install_path: str | None = None
        self.binary_path: Path | None = None
        self.extracted_dir: Path | None = None

    @property
    def name(self) -> str:
        """
        Get the component's name.

        Returns:
            Component name from config
        """
        if self.config and self.config.name:
            return self.config.name
        raise ComponentError("Component name not found in config")

    def _install_path(self, component: str) -> str:
        """
        Get binary path from specified component.

        Returns:
            Binary path of the specified component
        """
        if component_instance := self.instances.get(component):
            if component_instance.install_path:
                return component_instance.install_path

        raise ComponentError(f"Install path for component '{component}' not found")

    # Lifecycle hooks - all have default empty implementations
    # Override in subclass as needed

    def download_hook(self, arch: str) -> None:
        """
        Download component artifacts.

        This hook runs in the DOWNLOAD stage (can be parallelized).
        Override to implement download logic.

        Access component config via self.config (repo, release, installation).

        Args:
            arch: Architecture (amd64, arm64, etc.)
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        comp_name = self.config.name
        match self.config.installation.method:
            case InstallMethod.BINARY:
                self.binary_path = self.download_binary_from_config(arch, comp_name)
            case InstallMethod.BINARY_ARCHIVE:
                self.extracted_dir = self.download_and_extract_archive(arch)

    def pre_install_hook(self) -> None:
        """
        Prepare machine for component installation.

        This hook runs in the PRE_INSTALL stage (sequential).
        Override to implement machine preparation (swapoff, sysctl, etc.).
        """
        pass

    def install_hook(self, arch: str) -> None:
        """
        Install the component.

        This hook runs in the INSTALL stage (sequential,
        dependency-ordered). Override to implement installation logic.

        Access component config via self.config (repo, release, installation).

        Args:
            arch: Architecture (amd64, arm64, etc.)
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        comp_name = self.config.name
        match self.config.installation.method:
            case InstallMethod.BINARY:
                if not self.binary_path or not self.binary_path.exists():
                    raise ComponentError(
                        f"{comp_name} binary not downloaded. Run download hook first."
                    )
                self.install_path = self.install_downloaded_binary(self.binary_path)
            case InstallMethod.BINARY_ARCHIVE:
                if not self.extracted_dir or not self.extracted_dir.exists():
                    raise ComponentError(
                        f"{comp_name} archive not downloaded. Run download hook first."
                    )
                for each in self.extracted_dir.glob("*"):
                    installed = self.install_downloaded_binary(each, each.name)
                    if each.name == comp_name:
                        self.install_path = installed

    def bootstrap_hook(self) -> None:
        """
        Initialize and start the component.

        This hook runs in the BOOTSTRAP stage (sequential, dependency-ordered).
        Override to implement service startup logic.
        """
        pass

    def post_bootstrap_hook(self) -> None:
        """
        Post-initialization tasks.

        This hook runs in the POST_BOOTSTRAP stage (sequential).
        Override to implement post-init configuration.
        """
        pass

    def configure_hook(self) -> None:
        """
        Configure the component (create config files, etc.).

        This hook runs in the CONFIGURE stage before BOOTSTRAP (sequential).
        Override to implement configuration logic.
        """
        pass

    def verify_hook(self) -> None:
        """
        Verify the component is working correctly.

        This hook runs in the VERIFY stage (sequential).
        Override to implement health check logic.
        """
        pass

    def test_hook(self) -> None:
        """
        Run tests on the component.

        This hook runs in the TEST stage (sequential).
        Override to implement testing logic (e.g., spread tests).
        """
        pass

    def remove_hook(self) -> None:
        """
        Remove/uninstall the component.

        This hook runs during component removal.
        Override to implement cleanup logic.
        """
        pass

    # Component directory and alternatives management methods
    @property
    def component_dir(self) -> str:
        """
        Get the component's installation directory.

        Returns:
            Path to /opt/kube-galaxy/{self.name}/
        """
        return str(SystemPaths.component_dir(self.name))

    @property
    def component_tmp_dir(self) -> str:
        """
        Get the component's secure temporary directory.

        Returns:
            Path to /opt/kube-galaxy/{self.name}/tmp/
        """
        return str(SystemPaths.component_temp_dir(self.name))

    def register_alternative(self, binary_name: str, binary_path: str) -> None:
        """
        Register a binary with update-alternatives.

        Args:
            binary_name: Name of the binary (e.g., 'containerd')
            binary_path: Full path to the binary
        """
        try:
            alternative_path = f"{SystemPaths.USR_LOCAL_BIN}/{binary_name}"
            run(
                [
                    *Commands.UPDATE_ALTERNATIVES_INSTALL,
                    alternative_path,
                    binary_name,
                    binary_path,
                    Permissions.ALTERNATIVES_PRIORITY,
                ],
                check=True,
            )
        except Exception as e:
            raise ComponentError(f"Failed to register alternative for {binary_name}: {e}") from e

    def remove_component_alternatives(self) -> None:
        """
        Remove all alternatives for binaries in this component's bin directory.
        """
        component_bin_dir = Path(self.component_dir) / "bin"
        if component_bin_dir.exists():
            for binary in component_bin_dir.glob("*"):
                if binary.is_file():
                    try:
                        run(
                            [*Commands.UPDATE_ALTERNATIVES_REMOVE, binary.name, str(binary)],
                            check=False,
                        )  # Don't fail if alternative doesn't exist
                    except Exception:
                        pass  # Ignore errors during cleanup

    def cleanup_component_dir(self) -> None:
        """
        Remove the entire component directory.
        """
        try:
            run([*Commands.SUDO_RM_RF, self.component_dir], check=False)
        except Exception:
            pass  # Ignore errors during cleanup

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
        pass

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
        Ensure component temp directory exists and return path.

        Returns:
            Path to component temp directory
        """
        temp_dir = Path(self.component_tmp_dir)
        run([*Commands.SUDO_MKDIR_P, str(temp_dir)], check=True)
        return temp_dir

    def download_binary_from_config(self, arch: str, binary_name: str | None = None) -> Path:
        """
        Download binary using component config source_format.

        Args:
            arch: Architecture string for URL template
            binary_name: Optional override for binary filename

        Returns:
            Path to downloaded binary

        Raises:
            ComponentError: If download fails or config missing
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        repo = self.config.repo
        release = self.config.release
        source_format = self.config.installation.source_format

        # Construct download URL from source_format template
        url = source_format.format(repo=repo, release=release, arch=arch)
        filename = binary_name or url.split("/")[-1]

        # Download to secure temporary directory
        temp_dir = self.ensure_temp_dir()
        binary_path = temp_dir / filename
        download_file(url, binary_path)

        return binary_path

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
        install_path = install_binary(binary_path, name, self.name)
        self.install_path = install_path
        return install_path

    def download_and_extract_archive(self, arch: str, extract_dir: Path | None = None) -> Path:
        """
        Download and extract archive from config.

        Args:
            arch: Architecture string (e.g., 'amd64')
            extract_dir: Custom extraction directory (optional)

        Returns:
            Path to extraction directory

        Raises:
            ComponentError: If download or extraction fails
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        repo = self.config.repo
        release = self.config.release
        source_format = self.config.installation.source_format

        # Construct download URL from source_format template
        url = source_format.format(repo=repo, release=release, arch=arch)
        filename = url.split("/")[-1]

        # Download to temp directory
        temp_dir = self.ensure_temp_dir()
        archive_path = temp_dir / filename
        download_file(url, archive_path)

        # Extract archive
        extract_destination = extract_dir or (temp_dir / "extracted")
        extract_destination.mkdir(exist_ok=True)
        extract_archive(archive_path, extract_destination)

        return extract_destination

    def start_systemd_service(self, service_name: str) -> None:
        """
        Enable and start a systemd service.

        Args:
            service_name: Name of the service

        Raises:
            ComponentError: If service operations fail
        """
        try:
            run([*Commands.SYSTEMCTL_DAEMON_RELOAD], check=True)
            run([*Commands.SYSTEMCTL_ENABLE, service_name], check=True)
            run([*Commands.SYSTEMCTL_START, service_name], check=True)
        except Exception as e:
            raise ComponentError(f"Failed to start {service_name} service: {e}") from e

    def stop_systemd_service(self, service_name: str) -> None:
        """
        Stop and disable a systemd service (best effort).

        Args:
            service_name: Name of the service
        """
        try:
            run([*Commands.SYSTEMCTL_STOP, service_name], check=False)
            run(["sudo", "systemctl", "disable", service_name], check=False)
            info(f"Stopped {service_name} service")
        except Exception as e:
            info(f"Failed to stop {service_name} service: {e}")

    def create_systemd_service(
        self, service_name: str, service_content: str, system_location: bool = True
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
            # Write to temp file first
            temp_dir = self.ensure_temp_dir()
            temp_unit = temp_dir / f"{service_name}.service"
            run([*Commands.SUDO_TEE, str(temp_unit)], input=service_content, text=True, check=True)

            # Create target directory and copy
            target_dir = "/etc/systemd/system" if system_location else "/usr/lib/systemd/system"
            target_path = f"{target_dir}/{service_name}.service"
            run([*Commands.SUDO_MKDIR_P, target_dir], check=True)
            run([*Commands.SUDO_CP, str(temp_unit), target_path], check=True)
        except Exception as e:
            raise ComponentError(f"Failed to create {service_name} service: {e}") from e

    def write_config_file(
        self, config_content: str, target_path: str, mode: str = Permissions.READABLE
    ) -> None:
        """
        Write configuration content to a file via temporary file.

        Args:
            config_content: Configuration file content
            target_path: Final path for config file
            mode: File permissions (default: 644)

        Raises:
            ComponentError: If file writing fails
        """
        try:
            temp_dir = self.ensure_temp_dir()
            temp_config = temp_dir / "config"

            # Write to temp file, then copy and set permissions
            run([*Commands.SUDO_TEE, str(temp_config)], input=config_content, text=True, check=True)
            run([*Commands.SUDO_MKDIR_P, str(Path(target_path).parent)], check=True)
            run([*Commands.SUDO_CP, str(temp_config), target_path], check=True)
            run([*Commands.SUDO_CHMOD, mode, target_path], check=True)
        except Exception as e:
            raise ComponentError(f"Failed to write config to {target_path}: {e}") from e

    def verify_systemd_service(self, service_name: str) -> None:
        """
        Verify that a systemd service is running.

        Args:
            service_name: Name of the service

        Raises:
            ComponentError: If service is not active
        """
        try:
            run(["sudo", "systemctl", "is-active", service_name], check=True)
        except Exception as e:
            raise ComponentError(f"Service {service_name} is not active: {e}") from e

    def verify_binary_works(self, binary_name: str, args: list[str] | None = None) -> None:
        """
        Verify that a binary command works.

        Args:
            binary_name: Name of the binary to test
            args: Arguments to pass to binary (default: ['--version'])

        Raises:
            ComponentError: If binary command fails
        """
        test_args = args or ["--version"]
        try:
            run([binary_name, *test_args], check=True)
        except Exception as e:
            raise ComponentError(f"Binary {binary_name} verification failed: {e}") from e

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
                    run([*Commands.SUDO_RM_RF, str(dir_path)], check=False)
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
            config_file = Path(config_path)
            if config_file.exists():
                try:
                    run(["sudo", "rm", "-f", str(config_file)], check=False)
                    info(f"Removed {name} config: {config_file}")
                except Exception as e:
                    info(f"Failed to remove {config_file}: {e}")

    def remove_installed_binary(self) -> None:
        """
        Remove the installed binary if it exists.
        """
        if self.install_path and Path(self.install_path).exists():
            Path(self.install_path).unlink()
            info(f"Removed {self.name} binary: {self.install_path}")
