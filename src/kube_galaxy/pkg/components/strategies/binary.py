"""Install hooks for InstallMethod.BINARY."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kube_galaxy.pkg.utils.components import download_file, format_component_pattern
from kube_galaxy.pkg.utils.errors import ComponentError

from ._base import _InstallStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _download(comp: ComponentBase) -> None:
    install_cfg = comp.config.installation
    src = format_component_pattern(
        install_cfg.source_format,
        comp.config,
        comp.arch_info,
        install_cfg.repo,
    )
    temp_dir = comp.ensure_temp_dir()
    filepath = temp_dir / src.split("/")[-1]
    download_file(src, filepath)
    comp.binary_path = filepath


def _install(comp: ComponentBase) -> None:
    if not comp.binary_path or not comp.binary_path.exists():
        raise ComponentError(f"{comp.name} binary not downloaded. Run download hook first.")
    comp.install_path = comp.install_downloaded_binary(comp.binary_path)


_BinaryInstallStrategy = _InstallStrategy(download=_download, install=_install)
