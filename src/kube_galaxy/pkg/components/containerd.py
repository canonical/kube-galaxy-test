"""
Containerd component installation and management.

Containerd is the container runtime used by Kubernetes clusters.
"""

from typing import ClassVar

from kube_galaxy.pkg.components import ComponentBase, register_component
from kube_galaxy.pkg.literals import Commands, Permissions
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.shell import run


@register_component
class Containerd(ComponentBase):
    """
    Containerd container runtime component.

    Handles downloading, installing, and starting the containerd
    container runtime for Kubernetes.
    """

    # Component metadata
    CATEGORY = "containerd"
    DEPENDENCIES: ClassVar[list[str]] = ["runc"]

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 300  # 5 minutes (containerd archive can be large)
    INSTALL_TIMEOUT = 120  # 2 minutes (extract and copy)
    BOOTSTRAP_TIMEOUT = 60  # 1 minute (start service)
    CONFIGURE_TIMEOUT = 60  # 1 minute (verify service running)
    BIN_PATH = "bin/*"  # Path inside archive where containerd binary is located

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

    def pre_install_hook(self) -> None:
        """Remove any existing containerd installation to avoid conflicts."""
        info("  Removing existing containerd installation if present")
        run([*Commands.SUDO_APT_REMOVE, "-y", "containerd.io"], check=False)

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
        self.write_config_file(
            config_content, "/etc/containerd/config.toml", mode=Permissions.READABLE
        )

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

        self.create_systemd_service("containerd", systemd_unit, enabled=True)

    def bootstrap_hook(self) -> None:
        """
        Start containerd service.
        """
        run([*Commands.SYSTEMCTL_START, "containerd"], check=True)

    def verify_hook(self) -> None:
        """
        Verify containerd is running and functional.

        Checks service status and command availability.
        """
        # Check service is active
        run([*Commands.SYSTEMCTL_IS_ACTIVE, "containerd"], check=True)

        # Check containerd command works
        run(["containerd", "--version"], check=True)

    def stop_hook(self) -> None:
        """
        Stop the containerd service and remove containers/images.

        This is a destructive process that removes all container runtime data.
        """
        try:
            # Stop containerd service
            run([*Commands.SYSTEMCTL_STOP, "containerd"], check=False)
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
            "/etc/containerd/config.toml",
            "/etc/systemd/system/containerd.service",
        ]
        self.remove_config_files(config_files)

    def post_delete_hook(self) -> None:
        """
        Clean up containerd data directories and disable systemd service.
        """
        # Disable and reload systemd if service still exists
        try:
            run([*Commands.SYSTEMCTL_DISABLE, "containerd"], check=False)
            run([*Commands.SYSTEMCTL_DAEMON_RELOAD], check=False)
            info("Disabled containerd service")
        except Exception:
            pass

        # Remove containerd data directories (destructive cleanup)
        containerd_dirs = [
            "/var/lib/containerd",
            "/run/containerd",
            "/etc/containerd",
        ]
        self.remove_directories(containerd_dirs)

        # Clean up temporary extraction directory if it exists
        if self.extracted_dir and self.extracted_dir.exists():
            self.remove_directories([str(self.extracted_dir)])
