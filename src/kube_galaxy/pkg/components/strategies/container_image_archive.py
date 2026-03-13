"""Install hooks for InstallMethod.CONTAINER_IMAGE_ARCHIVE."""

from __future__ import annotations

import bz2
import gzip
import lzma
import shutil
from typing import TYPE_CHECKING

from kube_galaxy.pkg.utils.components import download_file, format_component_pattern
from kube_galaxy.pkg.utils.errors import ComponentError

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
    file_path = temp_dir / url.split("/")[-1]
    download_file(url, file_path)
    if extracted_dir := comp.extracted_dir:
        extracted_dir.mkdir(exist_ok=True)
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


_ContainerImageArchiveInstallStrategy = _InstallStrategy(download=_download)
