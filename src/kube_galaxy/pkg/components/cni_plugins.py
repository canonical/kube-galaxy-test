"""
CNI-plugins component installation and management.
"""

from pathlib import Path
from textwrap import dedent

from kube_galaxy.pkg.components import ComponentBase, register_component
from kube_galaxy.pkg.literals import Permissions
from kube_galaxy.pkg.manifest.models import InstallMethod
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info


@register_component("cni-plugins")
class CNIPlugins(ComponentBase):
    """
    CNI-plugins component for container networking.

    This component handles container networking and network policies.
    """

    # Timeout configuration (in seconds)
    OPT_CNI_PLUGINS_DIR = Path("/opt/cni/bin")
    LOOPBACK_CONFIG_PATH = Path("/etc/cni/net.d/10-loopback.conf")

    def install_hook(self) -> None:
        """
        Install cni-plugins binary from extracted archive.

        Requires download_hook to have completed first.

        Args:
            arch: Architecture (amd64, arm64, etc.)
        """
        comp_name = self.config.name
        match self.config.installation.method:
            case InstallMethod.BINARY_ARCHIVE:
                if not self.extracted_dir or not self.extracted_dir.exists():
                    raise ComponentError(
                        f"{comp_name} archive not downloaded. Run download hook first."
                    )
                self.unit.run(["mkdir", "-p", str(self.OPT_CNI_PLUGINS_DIR)], privileged=True)
                for item in self.extracted_dir.iterdir():
                    if item.is_file() and item.stat().st_mode & 0o111:
                        info(f"    Symlink {comp_name} binary: {item.name}")
                        self.unit.run(
                            [
                                "ln",
                                "-s",
                                str(item),
                                str(self.OPT_CNI_PLUGINS_DIR / item.name),
                            ],
                            privileged=True,
                        )
                self.install_path = str(self.OPT_CNI_PLUGINS_DIR)
            case _:
                raise ComponentError(
                    f"Unsupported installation method for {comp_name}: "
                    f" {self.config.installation.method}"
                )

    def configure_hook(self) -> None:
        """Configure cni-plugins by creating a loopback configuration file."""
        loopback_content = dedent("""
        {
          "cniVersion": "0.4.0",
          "name": "lo",
          "type": "loopback"
        }""").strip()

        self.write_config_file(
            loopback_content, self.LOOPBACK_CONFIG_PATH, mode=Permissions.READABLE
        )

    def delete_hook(self) -> None:
        """
        Remove cni-plugin binaries, symlinks, and configuration files.
        """
        if self.extracted_dir and self.extracted_dir.exists():
            for item in self.extracted_dir.iterdir():
                if item.is_file() and item.stat().st_mode & 0o111:
                    info(f"    Removed {self.name} binary: {item.name}")
                    self.unit.run(
                        ["rm", "-rf", str(self.OPT_CNI_PLUGINS_DIR / item.name)],
                        privileged=True,
                        check=False,
                    )

        # This will handle alternatives and binaries
        super().delete_hook()

        # Remove cni-plugin configuration files
        config_files = [str(self.LOOPBACK_CONFIG_PATH)]
        self.remove_config_files(config_files)
