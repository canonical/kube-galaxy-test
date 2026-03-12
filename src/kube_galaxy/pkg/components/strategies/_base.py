"""Strategy records for install and test method hooks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _noop(comp: ComponentBase) -> None:
    pass


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
