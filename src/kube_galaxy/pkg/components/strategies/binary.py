"""Install hooks for InstallMethod.BINARY."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kube_galaxy.pkg.utils.components import download_file, format_component_pattern, source_locally
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.gh import gh_download_artifact

from ._base import _InstallStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _download(comp: ComponentBase) -> None:
    install_cfg = comp.config.installation
    url = format_component_pattern(
        install_cfg.source_format,
        comp.config,
        comp.arch_info,
        install_cfg.repo,
    )
    temp_dir = comp.ensure_temp_dir()
    filepath = temp_dir / url.split("/")[-1]
    if install_cfg.repo.is_local:
        source_locally(comp.name, url, filepath)
    elif install_cfg.repo.is_gh_artifact:
        gh_download_artifact(comp.name, url, filepath)
    else:
        download_file(url, filepath)
    comp.binary_path = filepath


def _install(comp: ComponentBase) -> None:
    if not comp.binary_path or not comp.binary_path.exists():
        raise ComponentError(f"{comp.name} binary not downloaded. Run download hook first.")
    comp.install_path = comp.install_downloaded_binary(comp.binary_path)


_BinaryInstallStrategy = _InstallStrategy(download=_download, install=_install)
