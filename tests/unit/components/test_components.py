import importlib
import inspect
from pathlib import Path

from kube_galaxy.pkg.components import COMPONENTS, register_component
from kube_galaxy.pkg.components._base import ComponentBase


def test_components_registered_from_modules() -> None:
    """Ensure ComponentBase subclasses defined in modules are registered.

    The test iterates over all python modules in the `kube_galaxy.pkg.components`
    package (skipping private modules) and for every class that is a
    `ComponentBase` subclass defined in that module asserts that the
    `COMPONENTS` registry contains an entry keyed by the lower-cased class name.
    """
    pkg = importlib.import_module("kube_galaxy.pkg.components")
    pkg_dir = Path(pkg.__file__).parent

    for py in pkg_dir.glob("*.py"):
        modname = py.stem
        if modname.startswith("_"):
            continue
        module = importlib.import_module(f"kube_galaxy.pkg.components.{modname}")

        for _name, obj in inspect.getmembers(module, inspect.isclass):
            # skip the base itself
            if obj is ComponentBase:
                continue

            # only consider classes defined in this module and subclassing ComponentBase
            if inspect.getmodule(obj) is module and issubclass(obj, ComponentBase):
                key = obj.__name__.lower()
                assert key in COMPONENTS, f"{obj!r} not registered as {key}"
                assert COMPONENTS[key] is obj


def test_register_component_decorator_registers_and_cleans_up() -> None:
    """Verify the `register_component` decorator adds the class to COMPONENTS.

    The test registers a temporary class and then removes it to avoid
    polluting global state for other tests.
    """

    @register_component
    class TempTestComponent(ComponentBase):
        pass

    try:
        assert "temptestcomponent" in COMPONENTS
        assert COMPONENTS["temptestcomponent"] is TempTestComponent
    finally:
        COMPONENTS.pop("temptestcomponent", None)
