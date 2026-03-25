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
    image_retag, image_source = (
        "",
        format_component_pattern(
            comp.config.installation.source_format,
            comp.config,
            comp.arch_info,
            comp.config.installation.repo,
        ),
    )
    if "://" in image_source:
        raise ComponentError(
            f"Container image installation does not support URL schemes for '{comp.name}'. "
            f"Use a plain Docker image reference (e.g. 'registry.k8s.io/image:tag')."
        )
    split = image_source.rsplit(":", 1)
    if len(split) != 2:
        raise ComponentError(f"Invalid container image format: {image_source}")
    source_repo, source_tag = split
    info(f"  Formatted container image: {source_repo}:{source_tag}")
    if comp.config.installation.retag_format:
        image_retag = format_component_pattern(
            comp.config.installation.retag_format,
            comp.config,
            comp.arch_info,
            comp.config.installation.repo,
        )

    mirror_path = None
    if mirror := comp.registry_mirror:
        # Strip registry hostname to derive the mirror storage path:
        # "registry.k8s.io/pause:3.10" -> "pause:3.10"
        # "ghcr.io/org/pause:3.10"     -> "org/pause:3.10"
        parts = source_repo.split("/", 1)
        mirror_path = f"{parts[1]}:{source_tag}" if len(parts) > 1 else image_source
        info(f"  Preloading image into registry mirror: {image_source} -> {mirror_path}")
        mirror.preload(f"docker://{image_source}", mirror_path)
    else:
        info(f"  No registry mirror configured; skipping preload for {image_source}")

    if mirror and mirror_path and image_retag:
        retag_repo, retag_tag = image_retag.rsplit(":", 1)
        parts = retag_repo.split("/", 1)
        retag_path = f"{parts[1]}:{retag_tag}" if len(parts) > 1 else image_retag
        info(f"  Retagging image in registry mirror: {mirror_path} -> {retag_path}")
        mirror.retag(mirror_path, retag_path)


_ContainerImageInstallStrategy = _InstallStrategy(download=_download)
