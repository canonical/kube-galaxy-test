"""
Base class for component installation and lifecycle management.

All component implementations should inherit from ComponentBase and
override the lifecycle hooks they need.
"""

import bz2
import gzip
import lzma
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import LiteralString, cast

import yaml

from kube_galaxy.pkg.arch.detector import ArchInfo
from kube_galaxy.pkg.literals import Commands, Permissions, SystemPaths, Timeouts
from kube_galaxy.pkg.manifest.models import ComponentConfig, InstallMethod, Manifest
from kube_galaxy.pkg.utils.client import apply_manifest
from kube_galaxy.pkg.utils.components import (
    download_file,
    extract_archive,
    format_component_pattern,
    install_binary,
)
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.shell import run


class ComponentBase:
    """
    Base class for Kubernetes component installation.

    Each component should subclass this and override the lifecycle hooks
    it needs. The component has access to:
    - The full manifest (self.manifest)
    - Its own component configuration (self.config)
    - Architecture information (self.arch_info)

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

    Use regular instance attributes for state management between hooks.
    """

    # Timeout configuration (in seconds) - override in subclass
    BOOTSTRAP_TIMEOUT = Timeouts.BOOTSTRAP_TIMEOUT

    # Component metadata - override in subclass
    BIN_PATH = "./*"  # Default path inside archive where binaries are located

    LOCAL_REGISTRY: LiteralString = "registry.k8s.io"

    def __init__(
        self,
        instances: dict[str, "ComponentBase"],
        manifest: Manifest,
        config: ComponentConfig,
        arch_info: ArchInfo,
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
        Get the cluster manager component instance.

        Returns:
            The instance of the cluster manager component

        Raises:
            ComponentError: If no cluster manager is found in instances
        """
        for instance in self.instances.values():
            if instance.is_cluster_manager:
                return cast("ClusterComponentBase", instance)
        raise ComponentError("No cluster manager component found in instances")

    # Lifecycle hooks - all have default empty implementations
    # Override in subclass as needed

    def download_hook(self) -> None:
        """
        Download component artifacts.

        This hook runs in the DOWNLOAD stage (can be parallelized).
        Override to implement download logic.

        Access component config via self.config (repo, release, installation).
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        arch = self.arch_info.k8s
        comp_name = self.config.name
        match self.config.installation.method:
            case InstallMethod.BINARY:
                self.binary_path = self.download_filename_from_config()
            case InstallMethod.BINARY_ARCHIVE:
                self.download_and_extract_archive(arch)
            case InstallMethod.CONTAINER_IMAGE_ARCHIVE:
                self.download_image_archive(arch)
            case InstallMethod.CONTAINER_IMAGE:
                self.container_format_repo_and_tag(arch)
            case InstallMethod.CONTAINER_MANIFEST:
                self.manifest_path = self.download_manifest_from_config(arch)
            case InstallMethod.NONE:
                pass
            case _:
                raise ComponentError(
                    f"Unsupported installation method for {comp_name}: "
                    f"{self.config.installation.method}"
                )
        match self.config.test:
            case True:
                info(f"Downloaded test artifacts for {comp_name}")
                self.download_tasks_from_config(arch)

    def pre_install_hook(self) -> None:
        """
        Prepare machine for component installation.

        This hook runs in the PRE_INSTALL stage (sequential).
        Override to implement machine preparation (swapoff, sysctl, etc.).
        """
        pass

    def install_hook(self) -> None:
        """
        Install the component.

        This hook runs in the INSTALL stage (sequential,
        dependency-ordered). Override to implement installation logic.

        Access component config via self.config (repo, release, installation).
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
                for each in self.extracted_dir.glob(self.BIN_PATH):
                    installed = self.install_downloaded_binary(each, each.name)
                    if each.name == comp_name:
                        self.install_path = installed
            case InstallMethod.CONTAINER_IMAGE:
                # TODO: Implement container image install logic
                pass
            case InstallMethod.CONTAINER_MANIFEST:
                # TODO: Implement manifest installation logic
                pass
            case InstallMethod.NONE:
                pass
            case _:
                raise ComponentError(
                    f"Unsupported installation method for {comp_name}: "
                    f"{self.config.installation.method}"
                )

    def bootstrap_hook(self) -> None:
        """
        Initialize and start the component.

        This hook runs in the BOOTSTRAP stage (sequential, dependency-ordered).
        Override to implement service startup logic.
        """

        if not self.config:
            raise ComponentError("Component config required for download")

        comp_name = self.config.name
        match self.config.installation.method:
            case InstallMethod.CONTAINER_MANIFEST:
                if not self.manifest_path or not self.manifest_path.exists():
                    raise ComponentError(
                        f"{comp_name} manifest not downloaded. Run download hook first."
                    )
                try:
                    apply_manifest(self.manifest_path)
                except ClusterError as e:
                    raise ComponentError(f"Failed to apply manifest for {comp_name}") from e

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
        if not self.config:
            raise ComponentError("Component config required for download")

        match self.config.installation.method:
            case InstallMethod.CONTAINER_MANIFEST:
                # Should check self.manifest_path exists before using it
                if not self.manifest_path or not self.manifest_path.exists():
                    raise ComponentError(f"{self.config.name} manifest not downloaded")

                # We can check rollout status of workloads defined in the manifest
                docs_str = run(
                    [*Commands.K_CREATE_DRY_RUN, "-f", str(self.manifest_path)],
                    check=True,
                    capture_output=True,
                )
                docs = list(yaml.safe_load_all(docs_str.stdout))
                workloads = [
                    doc
                    for doc in docs
                    if doc.get("kind") in ("Deployment", "DaemonSet", "StatefulSet")
                ]
                for workload in workloads:
                    kind = workload["kind"].lower()
                    name = workload["metadata"]["name"].lower()
                    namespace = workload["metadata"].get("namespace", "default").lower()
                    run(
                        [*Commands.K_ROLLOUT_STATUS, f"{kind}/{name}", "-n", namespace],
                        check=True,
                        timeout=self.BOOTSTRAP_TIMEOUT,
                    )

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

    @property
    def extracted_dir(self) -> Path | None:
        """Get the extracted directory for this component."""
        if not self.config:
            raise ComponentError("Component config required for extracted directory")
        if self.config.installation.method != InstallMethod.BINARY_ARCHIVE:
            return None
        return Path(self.component_tmp_dir) / "extracted"

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
        component_bin_dir = SystemPaths.component_bin_dir(self.name)
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
        shutil.rmtree(self.component_dir, ignore_errors=True)

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
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def download_filename_from_config(self) -> Path:
        """
        Download binary using component config source_format.

        Args:
            arch: Architecture string for URL template
            filename: Optional override for filename

        Returns:
            Path to downloaded filename

        Raises:
            ComponentError: If download fails or config missing
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        # Construct download URL from source_format template
        url = format_component_pattern(
            self.config.installation.source_format, self.config, self.arch_info
        )
        filename = url.split("/")[-1]

        # Download to secure temporary directory
        temp_dir = self.ensure_temp_dir()
        filepath = temp_dir / filename
        download_file(url, filepath)

        return filepath

    def download_and_extract_archive(self, arch: str) -> Path:
        """
        Download and extract archive from config.

        Args:
            arch: Architecture string (e.g., 'amd64')

        Returns:
            Path to extraction directory

        Raises:
            ComponentError: If download or extraction fails
        """
        archive_path = self.download_filename_from_config()
        if not self.extracted_dir:
            raise ComponentError("Extracted directory not defined for this component")

        # Extract archive
        self.extracted_dir.mkdir(exist_ok=True)
        extract_archive(archive_path, self.extracted_dir)

        return self.extracted_dir

    def download_image_archive(self, arch: str) -> None:
        """
        Download container image archive for this component.

        This is a placeholder for container image archive download logic, which may involve
        using 'ctr' or 'docker' commands to pull the specified image.
        """
        file_path = self.download_filename_from_config()
        if not self.extracted_dir:
            raise ComponentError("Extracted directory not defined for this component")

        # Extract if compressed archive; otherwise, assume it's a tar file containing the image
        self.extracted_dir.mkdir(exist_ok=True)
        image_tar = self.extracted_dir / "image.tar"
        if file_path.suffix == ".tar":
            file_path.rename(image_tar)
        elif file_path.suffixes == [".tar", ".gz"] or file_path.suffix == ".tgz":
            with gzip.open(file_path, "rb") as src, open(image_tar, "wb") as dst:
                shutil.copyfileobj(src, dst)
        elif file_path.suffixes == [".tar", ".xz"] or file_path.suffix == ".txz":
            with lzma.open(file_path, "rb") as src, open(image_tar, "wb") as dst:
                shutil.copyfileobj(src, dst)
        elif file_path.suffixes == [".tar", ".bz2"]:
            with bz2.open(file_path, "rb") as src, open(image_tar, "wb") as dst:
                shutil.copyfileobj(src, dst)
        else:
            raise ComponentError(f"Unsupported archive format for {file_path.name}")

    def download_tasks_from_config(self, arch: str) -> None:
        """
        Download test suite definition for this component.

        This is a placeholder for downloading test suite definitions, which may involve
        fetching task.yaml files or similar artifacts based on the component configuration.
        """
        # For example, we could download a task.yaml file using the same source_format logic
        # and place it in the appropriate tests directory for this component.
        pass

    def download_manifest_from_config(self, arch: str) -> Path:
        """
        Download Kubernetes manifest using component config source_format.

        Args:
            arch: Architecture string for URL template

        Returns:
            Path to downloaded manifest file

        Raises:
            ComponentError: If download fails or config missing
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        # Construct download URL from source_format template
        url = format_component_pattern(
            self.config.installation.source_format, self.config, self.arch_info
        )

        # Ensure https:// prefix for URLs like raw.githubusercontent.com
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Download to secure temporary directory
        temp_dir = self.ensure_temp_dir()
        filepath = temp_dir / f"{self.config.name}-manifest.yaml"
        download_file(url, filepath)
        info(f"Downloaded manifest for {self.config.name}")

        return filepath

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
        self.install_path = install_binary(binary_path, name, self.name)
        return self.install_path

    def container_format_repo_and_tag(self, arch: str) -> None:
        """
        Format container image repository and tag from config.

        Sets self.image_repository and self.image_tag based on config values.
        Args:
            arch: Architecture string (e.g., 'amd64')

        Returns:
            Path to extraction directory

        Raises:
            ComponentError: If download or extraction fails

        """
        if not self.config:
            raise ComponentError("Component config required for container image formatting")

        # Construct download URL from source_format template
        full = format_component_pattern(
            self.config.installation.source_format, self.config, self.arch_info
        )
        split = full.rsplit(":", 1)
        if len(split) != 2:
            raise ComponentError(f"Invalid container image format: {full}")
        self.image_repository, self.image_tag = split
        info(f"  Formatted container image: {self.image_repository}:{self.image_tag}")

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
            run([*Commands.SYSTEMCTL_DISABLE, service_name], check=False)
            info(f"Stopped {service_name} service")
        except Exception as e:
            info(f"Failed to stop {service_name} service: {e}")

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
            # Write to temp file first
            temp_dir = self.ensure_temp_dir()
            temp_unit = temp_dir / f"{service_name}.service"
            temp_unit.write_text(service_content)

            # Create target directory and copy
            target_dir = "/etc/systemd/system" if system_location else "/usr/lib/systemd/system"
            target_path = f"{target_dir}/{service_name}.service"
            run([*Commands.SUDO_MKDIR_P, target_dir], check=True)
            run([*Commands.SUDO_CP, str(temp_unit), target_path], check=True)

            # Reload systemd and enable service
            run([*Commands.SYSTEMCTL_DAEMON_RELOAD], check=True)
            if enabled:
                run([*Commands.SYSTEMCTL_ENABLE, service_name], check=True)
        except Exception as e:
            raise ComponentError(f"Failed to create {service_name} service: {e}") from e

    def write_config_file(
        self, config_content: str, target_path: str | Path, mode: str = Permissions.READABLE
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
            temp_config.write_text(config_content)

            # Write to temp file, then copy and set permissions
            run([*Commands.SUDO_MKDIR_P, str(Path(target_path).parent)], check=True)
            run([*Commands.SUDO_CP, str(temp_config), str(target_path)], check=True)
            run([*Commands.SUDO_CHMOD, mode, str(target_path)], check=True)
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
            run([*Commands.SYSTEMCTL_IS_ACTIVE, service_name], check=True)
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
            try:
                run([*Commands.SUDO_RM_RF, str(config_path)])
                info(f"Removed {name} config: {config_path}")
            except Exception as e:
                info(f"Failed to remove {config_path}: {e}")

    def remove_installed_binary(self) -> None:
        """
        Remove the installed binary if it exists.
        """
        if self.install_path and Path(self.install_path).exists():
            Path(self.install_path).unlink()
            info(f"Removed {self.name} binary: {self.install_path}")


class ClusterComponentBase(ComponentBase):
    """
    Base class for cluster components.

    kubeadm, kind, and other cluster lifecycle managers should inherit from this class.
    """

    def find_image_retag(self, image: str) -> str:
        """
        Find the retagged image name for a given image.

        Args:
            image: Original image name

        Returns:
            Retagged image name
        """
        return ""
