"""Test hooks for TestMethod.SPREAD."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.utils.components import format_component_pattern, source_locally
from kube_galaxy.pkg.utils.gh import gh_download_artifact

from ._base import _TestStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _download(comp: ComponentBase) -> None:
    """Download or copy the spread test suite for this component to the tests root.

    For **local** sources (``base-url: local``), the test suite is already
    present in the repository.  The ``source-format`` field in the test
    config is rendered via :func:`format_component_pattern` to produce the
    source path, which is then copied to the shared tests root so that the
    spread orchestrator can discover it alongside remotely-sourced test
    suites.

    For **remote** sources, the test suite must be cloned from the component
    repo.  The base implementation raises :class:`NotImplementedError`;
    subclasses or future additions can override this method to perform the
    actual clone via GitPython.
    """
    test_cfg = comp.config.test
    dest = SystemPaths.tests_root() / comp.name / SystemPaths.KUBE_GALAXY_TESTS_COMP_TASK
    src = format_component_pattern(
        test_cfg.source_format, comp.config, comp.arch_info, test_cfg.repo
    )

    if test_cfg.repo.is_local:
        source_locally(comp.name, src, dest)
    elif test_cfg.repo.is_gh_artifact:
        gh_download_artifact(comp.name, src, dest)
    else:
        raise NotImplementedError(
            f"Remote test suite download is not yet implemented for '{comp.name}'. "
            f"Use 'base-url: local' in the test block to ship test tasks inside this repo, "
            f"or manually place a task.yaml at {dest}/{SystemPaths.KUBE_GALAXY_TESTS_COMP_TASK}."
        )


_SpreadTestStrategy = _TestStrategy(download=_download)
