"""Install hooks for InstallMethod.BINARY_ARCHIVE."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kube_galaxy.pkg.utils.components import format_component_pattern, install_from_archive
from kube_galaxy.pkg.utils.errors import ComponentError

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
    # Download archive to the orchestrator staging area only; no local extraction needed.
    # Extraction is deferred to the install phase and performed on each node.
    comp.download_path = _fetch_to_temp(comp)


def _install(comp: ComponentBase) -> None:
    if not comp.download_path or not comp.download_path.exists():
        raise ComponentError(f"{comp.name} archive not downloaded. Run download hook first.")

    installed = install_from_archive(
        comp.download_path,
        _bin_path(comp),
        comp.name,
        comp.unit,
    )
    if comp.name in installed:
        comp.install_path = installed[comp.name]


_BinaryArchiveInstallStrategy = _InstallStrategy(download=_download, install=_install)
