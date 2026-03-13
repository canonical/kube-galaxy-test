"""Test hooks for TestMethod.SPREAD."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kube_galaxy.pkg.literals import SystemPaths
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
    src = format_component_pattern(
        test_cfg.source_format, comp.config, comp.arch_info, test_cfg.repo
    )
    dest = SystemPaths.tests_root() / comp.name / SystemPaths.KUBE_GALAXY_TESTS_COMP_TASK
    download_file(src, dest)


_SpreadTestStrategy = _TestStrategy(download=_download)
