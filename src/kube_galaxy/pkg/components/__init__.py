"""
Component installation and management modules.

Components inherit from ComponentBase and override the lifecycle hooks they need.
"""

import importlib as _importlib
import pkgutil as _pkgutil

from kube_galaxy.pkg.components._base import ComponentBase

__all__ = ["COMPONENTS", "ComponentBase", "register_component"]

# Simple mapping of component names to classes
COMPONENTS: dict[str, type[ComponentBase]] = {}


def register_component(cls: type[ComponentBase]) -> type[ComponentBase]:
    """Decorator to register a component class in the COMPONENTS registry
    Args:
        cls: The component class to register.
    Returns:
        The original class, unmodified
    """
    COMPONENTS[cls.__name__.lower()] = cls
    return cls


# Import all component modules so they execute registration side-effects

for _finder, modname, _ispkg in _pkgutil.iter_modules(__path__):
    if not modname.startswith("_"):  # Skip private modules
        _importlib.import_module(f"{__name__}.{modname}")
