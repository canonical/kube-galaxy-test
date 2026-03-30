"""
CNI-plugins component installation and management.
"""

from pathlib import Path
from textwrap import dedent

from kube_galaxy.pkg.components import ComponentBase, register_component
from kube_galaxy.pkg.literals import Permissions, SystemPaths
from kube_galaxy.pkg.manifest.models import InstallMethod
from kube_galaxy.pkg.utils.components import format_component_pattern, install_from_archive
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
        Install cni-plugins binaries from archive on the node.

        Requires download_hook to have completed first.
        Installs all extracted binaries to the component bin directory, then
        creates symlinks in /opt/cni/bin/ for each binary.
        """
        comp_name = self.config.name
        match self.config.installation.method:
            case InstallMethod.BINARY_ARCHIVE:
                if not self.download_path or not self.download_path.exists():
                    raise ComponentError(
                        f"{comp_name} binary archive not found. Run download hook first."
                    )
                bin_pattern = format_component_pattern(
                    self.config.installation.bin_path,
                    self.config,
                    self.arch_info,
                    self.config.installation.repo,
                )
                installed = install_from_archive(
                    self.download_path,
                    bin_pattern,
                    self.name,
                    self.unit,
                )
                self.unit.run(["mkdir", "-p", str(self.OPT_CNI_PLUGINS_DIR)], privileged=True)
                comp_bin_dir = SystemPaths.component_bin_dir(self.name)
                for binary_name in installed:
                    comp_bin = str(comp_bin_dir / binary_name)
                    info(f"    Symlink {comp_name} binary: {binary_name}")
                    self.unit.run(
                        ["ln", "-sf", comp_bin, str(self.OPT_CNI_PLUGINS_DIR / binary_name)],
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
        # Remove symlinks from /opt/cni/bin/ for each binary in the component bin dir
        comp_bin_dir = SystemPaths.component_bin_dir(self.name)
        result = self.unit.run(["ls", str(comp_bin_dir)], privileged=True, check=False)
        if result.returncode == 0:
            for binary_name in result.stdout.splitlines():
                info(f"    Removed {self.name} binary: {binary_name}")
                self.unit.run(
                    ["rm", "-rf", str(self.OPT_CNI_PLUGINS_DIR / binary_name)],
                    privileged=True,
                    check=False,
                )

        # This will handle alternatives and binaries
        super().delete_hook()

        # Remove cni-plugin configuration files
        config_files = [str(self.LOOPBACK_CONFIG_PATH)]
        self.remove_config_files(config_files)
