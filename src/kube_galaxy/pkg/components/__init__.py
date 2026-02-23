"""
Component installation and management modules.

Components inherit from ComponentBase and override the lifecycle hooks they need.
"""

import importlib as _importlib
import pkgutil as _pkgutil
from collections.abc import Callable

from kube_galaxy.pkg.components._base import ClusterComponentBase, ComponentBase
from kube_galaxy.pkg.utils.logging import info

__all__ = ["ClusterComponentBase", "ComponentBase", "find_component", "register_component"]

# Simple mapping of component names to classes
COMPONENTS: dict[str, type[ComponentBase]] = {}


def register_component(name: str) -> Callable[[type[ComponentBase]], type[ComponentBase]]:
    """Decorator to register a component class in the COMPONENTS registry

    Args:
        name: The name to register the component under.
    Returns:
        A decorator that registers the component class.
    """

    def decorator(cls: type[ComponentBase]) -> type[ComponentBase]:
        COMPONENTS[name.lower()] = cls
        return cls

    return decorator


def find_component(name: str) -> type[ComponentBase]:
    """Find a registered component class by name
    Args:
        name: The name of the component to find (case-insensitive)
    Returns:
        The component class if found, or ComponentBase if not found
    """
    if cls := COMPONENTS.get(name.lower()):
        info(f"Component '{name}' - found registered class '{cls.__name__}'")
        return cls

    info(f"Component '{name}' - loads default class")
    return ComponentBase


# Import all component modules so they execute registration side-effects

for _finder, modname, _ispkg in _pkgutil.iter_modules(__path__):
    if not modname.startswith("_"):  # Skip private modules
        _importlib.import_module(f"{__name__}.{modname}")
