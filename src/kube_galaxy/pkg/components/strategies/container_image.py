"""Install hooks for InstallMethod.CONTAINER_IMAGE."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kube_galaxy.pkg.utils.components import format_component_pattern
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info

from ._base import _InstallStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _download(comp: ComponentBase) -> None:
    install_cfg = comp.config.installation
    if install_cfg.repo.is_local:
        raise ComponentError(
            f"Container image installation does not support local for '{comp.name}'"
        )

    full = format_component_pattern(
        comp.config.installation.source_format,
        comp.config,
        comp.arch_info,
        comp.config.installation.repo,
    )
    split = full.rsplit(":", 1)
    if len(split) != 2:
        raise ComponentError(f"Invalid container image format: {full}")
    comp.image_repository, comp.image_tag = split
    info(f"  Formatted container image: {comp.image_repository}:{comp.image_tag}")


_ContainerImageInstallStrategy = _InstallStrategy(download=_download)
