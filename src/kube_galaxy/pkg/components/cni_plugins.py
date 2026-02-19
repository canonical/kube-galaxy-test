"""
CNI-plugins component installation and management.
"""

from pathlib import Path
from textwrap import dedent
from typing import ClassVar

from kube_galaxy.pkg.components import ComponentBase, register_component
from kube_galaxy.pkg.literals import Commands, Permissions
from kube_galaxy.pkg.manifest.models import InstallMethod
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.shell import run


@register_component
class CNIPlugins(ComponentBase):
    """
    CNI-plugins component for container networking.

    This component handles container networking and network policies.
    """

    # Component metadata
    CATEGORY = "container-networking"
    DEPENDENCIES: ClassVar[list[str]] = []

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 120  # 2 minutes
    INSTALL_TIMEOUT = 60  # 1 minute
    CONFIGURE_TIMEOUT = 60  # 1 minute
    VERIFY_TIMEOUT = 120  # 2 minutes
    OPT_CNI_PLUGINS_DIR = Path("/opt/cni/bin")
    LOOPBACK_CONFIG_PATH = Path("/etc/cni/net.d/10-loopback.conf")

    def install_hook(self, arch: str) -> None:
        """
        Install cni-plugins binary from extracted archive.

        Requires download_hook to have completed first.

        Args:
            arch: Architecture (amd64, arm64, etc.)
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        comp_name = self.config.name
        match self.config.installation.method:
            case InstallMethod.BINARY_ARCHIVE:
                if not self.extracted_dir or not self.extracted_dir.exists():
                    raise ComponentError(
                        f"{comp_name} archive not downloaded. Run download hook first."
                    )
                run([*Commands.SUDO_MKDIR_P, str(self.OPT_CNI_PLUGINS_DIR)], check=True)
                for item in self.extracted_dir.iterdir():
                    if item.is_file() and item.stat().st_mode & 0o111:
                        info(f"    Symlink {comp_name} binary: {item.name}")
                        run(
                            [
                                *Commands.SUDO_SYMLINK,
                                str(item),
                                str(self.OPT_CNI_PLUGINS_DIR / item.name),
                            ],
                            check=True,
                        )
                self.install_path = str(self.OPT_CNI_PLUGINS_DIR)
            case _:
                raise ComponentError(
                    f"Unsupported installation method for {comp_name}: "
                    f" {self.config.installation.method}"
                )

    def configure_hook(self) -> None:
        loopback_content = dedent("""
        {
          "cniVersion": "0.4.0",
          "name": "lo",
          "type": "loopback"
        }""").strip()

        self.write_config_file(
            loopback_content, str(self.LOOPBACK_CONFIG_PATH), mode=Permissions.READABLE
        )

    def delete_hook(self) -> None:
        """
        Remove cni-plugin binaries, and configuration files.
        """
        if not self.config:
            raise ComponentError("Component config required for download")

        # Remove update-alternatives entries for this component
        self.remove_component_alternatives()

        comp_name = self.config.name
        match self.config.installation.method:
            case InstallMethod.BINARY_ARCHIVE:
                if self.extracted_dir and self.extracted_dir.exists():
                    for item in self.extracted_dir.iterdir():
                        if item.is_file() and item.stat().st_mode & 0o111:
                            info(f"    Removed {comp_name} binary: {item.name}")
                            run([*Commands.SUDO_RM_RF, str(self.OPT_CNI_PLUGINS_DIR / item.name)])

        # Remove component directory (binaries)
        self.cleanup_component_dir()

        # Remove cni-plugin configuration files
        config_files = [str(self.LOOPBACK_CONFIG_PATH)]
        self.remove_config_files(config_files)
