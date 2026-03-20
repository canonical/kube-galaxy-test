"""Install hooks for InstallMethod.BINARY_ARCHIVE."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kube_galaxy.pkg.utils.components import (
    extract_archive,
    format_component_pattern,
)
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.paths import ensure_dir

from ._base import _fetch_to_temp, _InstallStrategy

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
    archive_path = _fetch_to_temp(comp)
    if extracted_dir := comp.extracted_dir:
        ensure_dir(extracted_dir)
    else:
        raise ComponentError(
            f"{comp.name} does not have an extracted_dir. Ensure the component config specifies "
            f"an appropriate installation method and that the component is being used correctly."
        )
    extract_archive(archive_path, extracted_dir)


def _install(comp: ComponentBase) -> None:
    if not comp.extracted_dir or not comp.extracted_dir.exists():
        raise ComponentError(f"{comp.name} archive not downloaded. Run download hook first.")
    for each in comp.extracted_dir.glob(_bin_path(comp)):
        installed = comp.install_downloaded_binary(each, each.name)
        if each.name == comp.name:
            comp.install_path = installed


_BinaryArchiveInstallStrategy = _InstallStrategy(download=_download, install=_install)
