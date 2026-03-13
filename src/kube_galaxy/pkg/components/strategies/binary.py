"""Install hooks for InstallMethod.BINARY."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kube_galaxy.pkg.utils.errors import ComponentError

from ._base import _fetch_to_temp, _InstallStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _download(comp: ComponentBase) -> None:
    comp.binary_path = _fetch_to_temp(comp)


def _install(comp: ComponentBase) -> None:
    if not comp.binary_path or not comp.binary_path.exists():
        raise ComponentError(f"{comp.name} binary not downloaded. Run download hook first.")
    comp.install_path = comp.install_downloaded_binary(comp.binary_path)


_BinaryInstallStrategy = _InstallStrategy(download=_download, install=_install)
