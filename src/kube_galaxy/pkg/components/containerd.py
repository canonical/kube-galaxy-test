"""
Containerd component installation and management.

Containerd is the container runtime used by Kubernetes clusters.
"""

import base64
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kube_galaxy.pkg.components import ClusterComponentBase, ComponentBase, register_component
from kube_galaxy.pkg.literals import Commands, Permissions
from kube_galaxy.pkg.manifest.models import InstallMethod
from kube_galaxy.pkg.utils.components import format_component_pattern
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.shell import run

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def _image_pull_and_retag(cluster_manager: ClusterComponentBase, image: ComponentBase) -> None:
    """
    Pull a container image with containerd and retag for use in the cluster.

    Args:
        cluster_manager: Cluster manager component defining image list
        image: Component with CONTAINER_IMAGE method to pull
    """
    # Use ctr to pull images directly into containerd
    to_pull = f"{image.image_repository}:{image.image_tag}"
    info(f"    Pulling image: {to_pull}")
    run([*Commands.SUDO_CTR_IMAGES, "pull", to_pull], check=True, stdout=subprocess.DEVNULL)
    if to_tag := cluster_manager.find_image_retag(to_pull):
        info(f"    Retag pulled image: {to_pull} -> {to_tag}")
        run([*Commands.SUDO_CTR_IMAGES, "tag", to_pull, to_tag], check=True)
    else:
        info(f"    No retag found for image: {to_pull}")


def _auths() -> dict[str, tuple[str, str]]:
    """
    Build a mapping of container registry hosts to (username, password) tuples for authentication.

    This helper inspects environment variables to determine registry credentials
    and returns a mapping of registry hostnames to (username, password) pairs.

    Returns:
        A dictionary mapping registry hostnames to (username, password) tuples.
    """
    auth_items = {}
    if GITHUB_TOKEN:
        auth_items["ghcr.io"] = ("github", GITHUB_TOKEN)
    return auth_items


def _image_import_and_retag(cluster_manager: ClusterComponentBase, image: ComponentBase) -> None:
    """
    Import a container image archive with containerd and retag for use in the cluster.

    Args:
        cluster_manager: Cluster manager component defining image list
        image: Component with CONTAINER_IMAGE_ARCHIVE method to import
    """
    # Use ctr to import images directly into containerd

    if not image.extracted_dir:
        raise ComponentError(
            f"Image archive for {image.config.name} not extracted. Run download hook first."
        )

    tar_archive = str(image.extracted_dir / "image.tar")
    before = run(
        [*Commands.SUDO_CTR_IMAGES, "list", "--quiet"],
        capture_output=True,
        text=True,
        check=True,
    )
    run([*Commands.SUDO_CTR_IMAGES, "import", tar_archive], check=True)
    after = run(
        [*Commands.SUDO_CTR_IMAGES, "list", "--quiet"],
        capture_output=True,
        text=True,
        check=True,
    )
    new_images = set(after.stdout.splitlines()) - set(before.stdout.splitlines())
    for img in new_images:
        if to_tag := cluster_manager.find_image_retag(img):
            info(f"    Retag imported image: {img} -> {to_tag}")
            run([*Commands.SUDO_CTR_IMAGES, "tag", img, to_tag], check=True)
        else:
            info(f"    No retag found for imported image: {img}")


@register_component("containerd")
class Containerd(ComponentBase):
    """
    Containerd container runtime component.

    Handles downloading, installing, and starting the containerd
    container runtime for Kubernetes.
    """

    # Timeout configuration (in seconds)
    MAX_IMAGE_PULL_WORKERS = 10
    SOCKET_PATH = Path("/run/containerd/containerd.sock")

    def _get_pause_image(self) -> str:
        """
        Get pause image from pause component or use default.

        Checks if pause component is loaded in the components dict
        and uses its configuration for the sandbox_image.

        Returns:
            Pause image URL to use in containerd config
        """
        # Fallback to default if no pause component
        image_format = "registry.k8s.io/pause:3.9"
        if pause := self.components.get("pause"):
            # Use source_format if it's a container image
            install = pause.config.installation
            if (
                install.method
                in [InstallMethod.CONTAINER_IMAGE_ARCHIVE, InstallMethod.CONTAINER_IMAGE]
                and install.source_format
            ):
                image_format = pause.config.installation.source_format
            # Otherwise construct from release version
            elif pause.config.release:
                image_format = f"registry.k8s.io/pause:{pause.config.release}"

        return format_component_pattern(image_format, self.config, self.arch_info)

    def _image_comps_by_type(self) -> tuple[list[ComponentBase], list[ComponentBase]]:
        """
        Get lists of tagged images and image archives components.

        Returns:
            Tuple of (tagged_images, image_archives)
        """
        tagged_images = []
        image_archives = []
        for comp in self.components.values():
            match comp.config.installation.method:
                case InstallMethod.CONTAINER_IMAGE:
                    tagged_images.append(comp)
                case InstallMethod.CONTAINER_IMAGE_ARCHIVE:
                    image_archives.append(comp)
        return tagged_images, image_archives

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

        for host, (username, password) in _auths().items():
            basic_auth = f"{username}:{password}".encode()
            content = f"""server = "{host}"

[host.https://{host}"]
  capabilities = ["pull", "resolve"]

  [host."https://{host}".header]
    Authorization = ["Basic {base64.b64encode(basic_auth).decode()}"]
"""
            self.write_config_file(
                content, f"/etc/containerd/certs.d/{host}/hosts.toml", mode=Permissions.PRIVATE
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
        run([*Commands.SYSTEMCTL_IS_ACTIVE, "--wait", "containerd"], check=True)

        start = time.time()
        while not self.SOCKET_PATH.exists():
            if time.time() - start > self.BOOTSTRAP_TIMEOUT:
                raise TimeoutError(
                    f"Socket {self.SOCKET_PATH} did not appear within {self.BOOTSTRAP_TIMEOUT}s"
                )
            time.sleep(0.1)

        images_tagged, image_archives = self._image_comps_by_type()
        cluster_manager = self.get_cluster_manager()
        with ThreadPoolExecutor(max_workers=self.MAX_IMAGE_PULL_WORKERS) as executor:
            # Pull and retag images in parallel
            pull_futures = []
            for image in images_tagged:
                info(f"  Pull and retag image from {image.config.name} component")
                future = executor.submit(_image_pull_and_retag, cluster_manager, image)
                pull_futures.append(future)

            # Import and retag image archives in parallel
            import_futures = []
            for image in image_archives:
                info(f"  Import image archive from {image.config.name} component")
                future = executor.submit(_image_import_and_retag, cluster_manager, image)
                import_futures.append(future)

            # Wait for all operations to complete
            for future in pull_futures + import_futures:
                future.result()  # This will raise any exceptions that occurred

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
        super().delete_hook()  # This will handle alternatives and binaries

        # Remove containerd configuration files
        config_files = [
            "/etc/containerd/config.toml",
            "/etc/systemd/system/containerd.service",
            *[f"/etc/containerd/certs.d/{host}/hosts.toml" for host in _auths().keys()],
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
