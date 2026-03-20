"""Test hooks for TestMethod.SPREAD."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.units.local import LocalUnit
from kube_galaxy.pkg.utils.components import download_file, format_component_pattern

from ._base import _TestStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _download(comp: ComponentBase) -> None:
    """Download the spread test suite for this component to the tests root.

    The ``source-format`` field in the test config is rendered via
    :func:`format_component_pattern` then passed directly to
    :func:`~kube_galaxy.pkg.utils.components.download_file`, which dispatches
    on URL scheme:
    """
    test_cfg = comp.config.test
    url = format_component_pattern(
        test_cfg.source_format, comp.config, comp.arch_info, test_cfg.repo
    )
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "download"
    dest = comp.ensure_temp_dir() / filename
    download_file(url, dest)
    remote = SystemPaths.local_tests_root() / comp.name / SystemPaths.KUBE_GALAXY_TESTS_COMP_TASK
    unit = LocalUnit()
    unit.put(dest, str(remote))


_SpreadTestStrategy = _TestStrategy(download=_download)
