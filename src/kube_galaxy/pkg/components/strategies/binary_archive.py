"""Install hooks for InstallMethod.BINARY_ARCHIVE."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from kube_galaxy.pkg.utils.components import (
    download_file,
    extract_archive,
    format_component_pattern,
    source_locally,
)
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.gh import gh_download_artifact

from ._base import _InstallStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _bin_path(comp: ComponentBase) -> str:
    return format_component_pattern(
        comp.config.installation.bin_path,
        comp.config,
        comp.arch_info,
        comp.config.installation.repo,
    )


def _download(comp: ComponentBase) -> None:
    install_cfg = comp.config.installation
    url = format_component_pattern(
        install_cfg.source_format,
        comp.config,
        comp.arch_info,
        install_cfg.repo,
    )
    temp_dir = comp.ensure_temp_dir()
    archive_path = temp_dir / url.split("/")[-1]
    if install_cfg.repo.is_local:
        source_locally(comp.name, url, archive_path)
    elif install_cfg.repo.is_gh_artifact:
        gh_download_artifact(comp.name, url, archive_path)
    else:
        download_file(url, archive_path)
    extracted_dir = Path(comp.component_tmp_dir) / "extracted"
    extracted_dir.mkdir(exist_ok=True)
    extract_archive(archive_path, extracted_dir)


def _install(comp: ComponentBase) -> None:
    if not comp.extracted_dir or not comp.extracted_dir.exists():
        raise ComponentError(f"{comp.name} archive not downloaded. Run download hook first.")
    for each in comp.extracted_dir.glob(_bin_path(comp)):
        installed = comp.install_downloaded_binary(each, each.name)
        if each.name == comp.name:
            comp.install_path = installed


_BinaryArchiveInstallStrategy = _InstallStrategy(download=_download, install=_install)
