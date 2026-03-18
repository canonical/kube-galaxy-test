"""
Containerd component installation and management.

Containerd is the container runtime used by Kubernetes clusters.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kube_galaxy.pkg.components import ClusterComponentBase, ComponentBase, register_component
from kube_galaxy.pkg.literals import Permissions
from kube_galaxy.pkg.manifest.models import InstallMethod
from kube_galaxy.pkg.utils.components import format_component_pattern
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.url import authentication_headers

HOSTS_D = Path("/etc/containerd/hosts.d")


def _registry_auth(component: "ComponentBase", host: str, auth: str) -> None:
    """
    Write a hosts.toml file for containerd registry authentication.

    This function generates the content for the hosts.toml file based on the provided
    registry host and authentication string, and writes it to the appropriate location
    under /etc/containerd/hosts.d/.

    Args:
        component: Container component instance to use for writing config files
        host: Registry hostname (e.g., "ghcr.io")
        auth: Authentication string (e.g., "Basic <base64-encoded-credentials>")
    """
    hosts_tmpl = Path(__file__).parent / "templates/containerd/hosts.toml"
    content = hosts_tmpl.read_text().format(host=host, authorization=auth)

    hosts_toml = HOSTS_D / host / "hosts.toml"
    component.write_config_file(content, hosts_toml, mode=Permissions.PRIVATE)


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
    image.unit.run(["crictl", "pull", to_pull], privileged=True)
    if to_tag := cluster_manager.find_image_retag(to_pull):
        info(f"    Retag pulled image: {to_pull} -> {to_tag}")
        image.unit.run(["ctr", "-n", "k8s.io", "images", "tag", to_pull, to_tag], privileged=True)
    else:
        info(f"    No retag found for image: {to_pull}")


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
    before_result = image.unit.run(
        ["ctr", "-n", "k8s.io", "images", "list", "--quiet"],
        privileged=True,
        check=True,
    )
    image.unit.run(["ctr", "-n", "k8s.io", "images", "import", tar_archive], privileged=True)
    after_result = image.unit.run(
        ["ctr", "-n", "k8s.io", "images", "list", "--quiet"],
        privileged=True,
        check=True,
    )
    new_images = set(after_result.stdout.splitlines()) - set(before_result.stdout.splitlines())
    for img in new_images:
        if to_tag := cluster_manager.find_image_retag(img):
            info(f"    Retag imported image: {img} -> {to_tag}")
            image.unit.run(
                ["ctr", "-n", "k8s.io", "images", "tag", img, to_tag], privileged=True
            )
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

            return format_component_pattern(image_format, pause.config, self.arch_info)
        return image_format

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
        self.unit.run(["apt", "remove", "-y", "containerd.io"], privileged=True, check=False)

    def configure_hook(self) -> None:
        """
        Configure containerd with proper Kubernetes-compatible settings.

        Generates default config, sets SystemdCgroup=true (required for K8s),
        configures pause image, and creates systemd service file.
        """
        # Generate default containerd config
        config_toml = Path(__file__).parent / "templates/containerd/config.toml"
        config_content = config_toml.read_text()

        # Configure pause image (sandbox_image) from pause component or default
        pause_image = self._get_pause_image()
        config_content = config_content.format(pause_image=pause_image)

        # Write containerd config to /etc/containerd/config.toml
        self.write_config_file(
            config_content, "/etc/containerd/config.toml", mode=Permissions.READABLE
        )

        for host, auth in authentication_headers(basic_auth=True).items():
            _registry_auth(self, host, auth)

        # Create systemd service unit
        systemd_unit = Path(__file__).parent / "templates/containerd/systemd_unit"
        self.create_systemd_service("containerd", systemd_unit.read_text(), enabled=True)

        # Configure crictl to target containerd
        crictl_tmpl = Path(__file__).parent / "templates/containerd/crictl.yaml"
        crictl_config = crictl_tmpl.read_text().format(socket_path=self.SOCKET_PATH)
        self.write_config_file(crictl_config, "/etc/crictl.yaml", mode=Permissions.READABLE)

    def bootstrap_hook(self) -> None:
        """
        Start containerd service.
        """
        self.unit.run(["systemctl", "start", "containerd"], privileged=True)
        self.unit.run(["systemctl", "is-active", "--wait", "containerd"], privileged=True)

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
        self.unit.run(["systemctl", "is-active", "containerd"], privileged=True)

        # Check containerd command works
        self.unit.run(["containerd", "--version"])

    def stop_hook(self) -> None:
        """
        Stop the containerd service and remove containers/images.

        This is a destructive process that removes all container runtime data.
        """
        try:
            # Stop containerd service
            self.unit.run(["systemctl", "stop", "containerd"], privileged=True, check=False)
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
            "/etc/containerd/hosts.d/",
            "/etc/crictl.yaml",
        ]
        self.remove_config_files(config_files)

    def post_delete_hook(self) -> None:
        """
        Clean up containerd data directories and disable systemd service.
        """
        # Disable and reload systemd if service still exists
        try:
            self.unit.run(["systemctl", "disable", "containerd"], privileged=True, check=False)
            self.unit.run(["systemctl", "daemon-reload"], privileged=True, check=False)
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
