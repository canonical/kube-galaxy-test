"""Strategy records for install and test method hooks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from kube_galaxy.pkg.utils.components import download_file, format_component_pattern

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _noop(comp: ComponentBase) -> None:
    pass


def _fetch_to_temp(comp: ComponentBase) -> Path:
    """Render ``installation.source-format``, download the result to the component temp dir.

    Returns the path of the downloaded file.
    """
    install_cfg = comp.config.installation
    url = format_component_pattern(
        install_cfg.source_format, comp.config, comp.arch_info, install_cfg.repo
    )
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "download"
    dest = comp.ensure_temp_dir() / filename
    download_file(url, dest)
    return dest


@dataclass
class _InstallStrategy:
    download: Callable[[ComponentBase], None] = _noop
    pre_install: Callable[[ComponentBase], None] = _noop
    install: Callable[[ComponentBase], None] = _noop
    configure: Callable[[ComponentBase], None] = _noop
    bootstrap: Callable[[ComponentBase], None] = _noop
    verify: Callable[[ComponentBase], None] = _noop
    remove: Callable[[ComponentBase], None] = _noop


@dataclass
class _TestStrategy:
    download: Callable[[ComponentBase], None] = _noop
    pre_install: Callable[[ComponentBase], None] = _noop
    install: Callable[[ComponentBase], None] = _noop
    configure: Callable[[ComponentBase], None] = _noop
    bootstrap: Callable[[ComponentBase], None] = _noop
    verify: Callable[[ComponentBase], None] = _noop
    remove: Callable[[ComponentBase], None] = _noop
