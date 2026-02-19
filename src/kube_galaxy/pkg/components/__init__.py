"""
Component installation and management modules.

Components inherit from ComponentBase and override the lifecycle hooks they need.
"""

import importlib as _importlib
import pkgutil as _pkgutil

from kube_galaxy.pkg.components._base import ComponentBase

__all__ = ["ComponentBase", "find_component", "register_component"]

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


def find_component(name: str) -> type[ComponentBase]:
    """Find a registered component class by name
    Args:
        name: The name of the component to find (case-insensitive)
    Returns:
        The component class if found, or ComponentBase if not found
    """
    remove = str.maketrans({".": "", "-": "", "_": ""})
    return COMPONENTS.get(name.lower().translate(remove)) or ComponentBase


# Import all component modules so they execute registration side-effects

for _finder, modname, _ispkg in _pkgutil.iter_modules(__path__):
    if not modname.startswith("_"):  # Skip private modules
        _importlib.import_module(f"{__name__}.{modname}")
