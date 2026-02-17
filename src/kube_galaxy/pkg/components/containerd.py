"""
Containerd component installation and management.

Containerd is the container runtime used by Kubernetes clusters.
"""

from pathlib import Path
from typing import ClassVar

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.utils.components import (
    download_file,
    extract_archive,
    install_binary,
)
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.shell import run


class Containerd(ComponentBase):
    """
    Containerd container runtime component.

    Handles downloading, installing, and starting the containerd
    container runtime for Kubernetes.
    """

    # Component metadata
    COMPONENT_NAME = "containerd"
    CATEGORY = "containerd"
    DEPENDENCIES: ClassVar[list[str]] = ["runc"]
    PRIORITY = 10

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 300  # 5 minutes (containerd archive can be large)
    INSTALL_TIMEOUT = 120  # 2 minutes (extract and copy)
    BOOTSTRAP_TIMEOUT = 60  # 1 minute (start service)
    CONFIGURE_TIMEOUT = 60  # 1 minute (verify service running)

    def _get_pause_image(self) -> str:
        """
        Get pause image from pause component or use default.

        Checks if pause component is loaded in the instances dict
        and uses its configuration for the sandbox_image.

        Returns:
            Pause image URL to use in containerd config
        """
        if pause := self.instances.get("pause"):
            # Use source_format if it's a container image
            if pause.config.installation.source_format:
                return pause.config.installation.source_format
            # Otherwise construct from release version
            if pause.config.release:
                return f"registry.k8s.io/pause:{pause.config.release}"

        # Fallback to default if no pause component
        return "registry.k8s.io/pause:3.9"

    def download_hook(self, arch: str) -> None:
        """
        Download containerd binary archive.

        Constructs download URL from self.config (repo, release, installation).
        Extracts archive for install hook.
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        repo = self.config.repo
        release = self.config.release
        source_format = self.config.installation.source_format

        # Construct download URL from source_format template
        url = source_format.format(repo=repo, release=release, arch=arch)
        filename = url.split("/")[-1]

        # Download to secure temporary directory
        temp_dir = Path(self.component_tmp_dir)
        run(["sudo", "mkdir", "-p", str(temp_dir)], check=True)

        archive_path = temp_dir / filename
        download_file(url, archive_path)

        # Extract archive
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir(exist_ok=True)
        extract_archive(archive_path, extract_dir)

        # Store paths as instance attribute
        self.extract_dir = extract_dir

    def pre_install_hook(self) -> None:
        """Remove any existing containerd installation to avoid conflicts."""
        info("  Removing existing containerd installation if present")
        run(["sudo", "apt", "remove", "-y", "containerd.io"], check=False)

    def install_hook(self, arch: str) -> None:
        """
        Install containerd binary from extracted archive.

        Requires download_hook to have completed first.
        """
        if not hasattr(self, "extract_dir") or not self.extract_dir.exists():
            raise ComponentError("containerd archive not downloaded. Run download hook first.")

        # Install binaries from extracted archive
        for each in (self.extract_dir / "bin").glob("*"):
            installed = install_binary(each, each.name, self.COMPONENT_NAME)
            if each.name == "containerd":
                self.install_path = installed

    def configure_hook(self) -> None:
        """
        Configure containerd with proper Kubernetes-compatible settings.

        Generates default config, sets SystemdCgroup=true (required for K8s),
        configures pause image, and creates systemd service file.
        """
        # Generate default containerd config
        result = run(
            ["containerd", "config", "default"],
            capture_output=True,
            text=True,
            check=True,
        )
        config_content = result.stdout

        # Set SystemdCgroup = true (required for Kubernetes)
        config_content = config_content.replace("SystemdCgroup = false", "SystemdCgroup = true")

        # Configure pause image (sandbox_image) from pause component or default
        pause_image = self._get_pause_image()
        config_content = config_content.replace(
            'sandbox_image = "registry.k8s.io/pause:3.8"',
            f'sandbox_image = "{pause_image}"',
        )

        # Write containerd config to /etc/containerd/config.toml
        run(["sudo", "mkdir", "-p", "/etc/containerd"], check=True)
        temp_config = Path(self.component_tmp_dir) / "config.toml"
        run(["sudo", "mkdir", "-p", str(temp_config.parent)], check=True)

        # Write config content to temp file with proper permissions
        run(["sudo", "tee", str(temp_config)], input=config_content, text=True, check=True)
        run(["sudo", "cp", str(temp_config), "/etc/containerd/config.toml"], check=True)
        run(["sudo", "chmod", "644", "/etc/containerd/config.toml"], check=True)

        # Create systemd service unit
        systemd_unit = """[Unit]
Description=containerd container runtime
Documentation=https://containerd.io
After=network.target local-fs.target

[Service]
ExecStart=/usr/local/bin/containerd
ExecStop=/bin/kill -s TERM $MAINPID
Restart=on-failure
RestartSec=5
Delegate=yes
KillMode=process
OOMScoreAdjust=-999
LimitNOFILE=1048576
LimitNPROC=infinity

[Install]
WantedBy=multi-user.target
"""

        # Write to temporary file first, then copy with sudo
        temp_unit = Path(self.component_tmp_dir) / "containerd.service"

        # Write service content to temp file with proper permissions
        run(["sudo", "tee", str(temp_unit)], input=systemd_unit, text=True, check=True)
        run(["sudo", "mkdir", "-p", "/etc/systemd/system"], check=True)
        run(["sudo", "cp", str(temp_unit), "/etc/systemd/system/containerd.service"], check=True)

        # Reload systemd and enable service
        run(["sudo", "systemctl", "daemon-reload"], check=True)
        run(["sudo", "systemctl", "enable", "containerd"], check=True)

    def bootstrap_hook(self) -> None:
        """
        Start containerd service.
        """
        run(["sudo", "systemctl", "start", "containerd"], check=True)

    def verify_hook(self) -> None:
        """
        Verify containerd is running and functional.

        Checks service status and command availability.
        """
        # Check service is active
        run(["sudo", "systemctl", "is-active", "containerd"], check=True)

        # Check containerd command works
        run(["containerd", "--version"], check=True)

    def stop_hook(self) -> None:
        """
        Stop the containerd service and remove containers/images.

        This is a destructive process that removes all container runtime data.
        """
        try:
            # Stop containerd service
            run(["sudo", "systemctl", "stop", "containerd"], check=False)
            info("Stopped containerd service")

            # TODO: Add crictl commands to remove containers and images
            # crictl rm --all
            # crictl rmi --all
            # Note: crictl may not be available during teardown

        except Exception as e:
            info(f"Failed to stop containerd service: {e}")

    def delete_hook(self) -> None:
        """
        Remove containerd alternatives, binaries, and configuration files.
        """
        # Remove update-alternatives entries for this component
        self.remove_component_alternatives()

        # Remove component directory (binaries)
        self.cleanup_component_dir()

        # Remove containerd configuration files
        config_files = [
            Path("/etc/containerd/config.toml"),
            Path("/etc/systemd/system/containerd.service"),
        ]

        for config in config_files:
            if config.exists():
                try:
                    run(["sudo", "rm", "-f", str(config)], check=False)
                    info(f"Removed config: {config}")
                except Exception as e:
                    info(f"Failed to remove {config}: {e}")

    def post_delete_hook(self) -> None:
        """
        Clean up containerd data directories and disable systemd service.
        """
        # Disable and reload systemd if service still exists
        try:
            run(["sudo", "systemctl", "disable", "containerd"], check=False)
            run(["sudo", "systemctl", "daemon-reload"], check=False)
            info("Disabled containerd service")
        except Exception:
            pass

        # Remove containerd data directories (destructive cleanup)
        containerd_dirs = [
            Path("/var/lib/containerd"),
            Path("/run/containerd"),
            Path("/etc/containerd"),
        ]

        for directory in containerd_dirs:
            if directory.exists():
                try:
                    run(["sudo", "rm", "-rf", str(directory)], check=False)
                    info(f"Removed containerd directory: {directory}")
                except Exception as e:
                    info(f"Failed to remove {directory}: {e}")

        # Clean up temporary extraction directory if it exists
        if hasattr(self, "extract_dir") and self.extract_dir.exists():
            try:
                run(["sudo", "rm", "-rf", str(self.extract_dir.parent)], check=False)
                info(f"Removed extraction directory: {self.extract_dir.parent}")
            except Exception as e:
                info(f"Failed to remove extraction directory: {e}")
