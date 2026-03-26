"""Install hooks for InstallMethod.CONTAINER_IMAGE_ARCHIVE."""

from __future__ import annotations

import bz2
import gzip
import lzma
import shutil
from typing import TYPE_CHECKING

from kube_galaxy.pkg.utils.components import format_component_pattern
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.paths import ensure_dir

from ._base import _fetch_to_temp, _InstallStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _download(comp: ComponentBase) -> None:
    file_path = _fetch_to_temp(comp)
    if extracted_dir := comp.extracted_dir:
        ensure_dir(extracted_dir)
    else:
        raise ComponentError(
            f"{comp.name} does not have an extracted_dir. Ensure the component config specifies "
            f"an appropriate installation method and that the component is being used correctly."
        )
    image_tar = extracted_dir / "image.tar"
    if file_path.suffix == ".tar":
        file_path.rename(image_tar)
    elif file_path.suffixes == [".tar", ".gz"] or file_path.suffix == ".tgz":
        with gzip.open(file_path, "rb") as src, open(image_tar, "wb") as dst:
            shutil.copyfileobj(src, dst)
    elif file_path.suffixes == [".tar", ".xz"] or file_path.suffix == ".txz":
        with lzma.open(file_path, "rb") as src, open(image_tar, "wb") as dst:
            shutil.copyfileobj(src, dst)
    elif file_path.suffixes == [".tar", ".bz2"]:
        with bz2.open(file_path, "rb") as src, open(image_tar, "wb") as dst:
            shutil.copyfileobj(src, dst)
    else:
        raise ComponentError(f"Unsupported archive format for {file_path.name}")

    if image_retag := comp.config.installation.retag_format:
        image_retag = format_component_pattern(
            comp.config.installation.retag_format,
            comp.config,
            comp.arch_info,
            comp.config.installation.repo,
        )

    mirror_path = None
    if mirror := comp.registry_mirror:
        mirror_path = mirror.inspect(f"docker-archive:{image_tar}")
        info(f"  Preloading image archive into registry mirror: {image_tar} -> {mirror_path}")
        mirror.preload(f"docker-archive:{image_tar}", mirror_path)

    if mirror and mirror_path and image_retag:
        retag_repo, retag_tag = image_retag.rsplit(":", 1)
        parts = retag_repo.split("/", 1)
        retag_path = f"{parts[1]}:{retag_tag}" if len(parts) > 1 else image_retag
        info(f"  Retagging image in registry mirror: {mirror_path} -> {retag_path}")
        mirror.retag(mirror_path, retag_path)


_ContainerImageArchiveInstallStrategy = _InstallStrategy(download=_download)
