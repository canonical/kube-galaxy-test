"""
Component installation and management modules.

Components inherit from ComponentBase and override the lifecycle hooks they need.

Component Lifecycle Hooks:
- download: Download binaries/containers (parallel with pooling)
- pre_install: Machine preparation (swapoff, sysctl, etc.)
- install: Install component binaries/configs
- bootstrap: Initialize services (e.g., kubeadm init)
- post_bootstrap: Post-initialization tasks (e.g., get kubeconfig)
- configure: Final configuration and verification
"""

import importlib
from enum import Enum


class HookStage(Enum):
    """Component lifecycle stages."""

    DOWNLOAD = "download"
    PRE_INSTALL = "pre_install"
    INSTALL = "install"
    BOOTSTRAP = "bootstrap"
    POST_BOOTSTRAP = "post_bootstrap"
    CONFIGURE = "configure"


# Registry of component classes
_COMPONENT_CLASSES: dict[str, type] = {}


def register_component_class(component_class: type) -> type:
    """
    Register a component class.

    Use as a decorator:
        @register_component_class
        class MyComponent(ComponentBase):
            ...

    Args:
        component_class: Class that inherits from ComponentBase

    Returns:
        The same class (for decorator usage)
    """
    if not hasattr(component_class, "COMPONENT_NAME"):
        raise ValueError(f"Component class {component_class} must define COMPONENT_NAME")

    _COMPONENT_CLASSES[component_class.COMPONENT_NAME] = component_class
    return component_class


def get_component_class(component_name: str) -> type | None:
    """
    Get registered class for a component.

    Args:
        component_name: Component identifier

    Returns:
        Component class if registered, None otherwise
    """
    return _COMPONENT_CLASSES.get(component_name)


def create_component_instance(component_name: str, manifest, component):
    """
    Create an instance of a component with manifest context.

    Args:
        component_name: Component identifier
        manifest: Full Manifest object
        component: Component configuration object

    Returns:
        Component instance or None if not found
    """
    component_class = get_component_class(component_name)
    if component_class:
        return component_class(manifest, component)
    return None


def get_all_component_classes() -> dict[str, type]:
    """Get all registered component classes."""
    return _COMPONENT_CLASSES.copy()


def get_component_module(component_name: str):
    """
    Dynamically import and return the component module.

    Args:
        component_name: Component identifier (e.g., 'containerd', 'etcd')

    Returns:
        The component module

    Raises:
        ImportError: If component module doesn't exist
    """
    # Normalize component name: replace hyphens with underscores
    module_name = component_name.replace("-", "_")
    try:
        return importlib.import_module(f"kube_galaxy.pkg.components.{module_name}")
    except ImportError as e:
        raise ImportError(
            f"Component '{component_name}' not found. "
            f"Expected module: kube_galaxy.pkg.components.{module_name}"
        ) from e


def install_component(
    component_name: str,
    repo: str,
    release: str,
    format: str,
    arch: str,
) -> None:
    """
    Install a component.

    Args:
        component_name: Component identifier
        repo: Repository URL
        release: Release/version tag
        format: Installation format (Binary, Container, Binary+Container)
        arch: Architecture (amd64, arm64, etc.)
    """
    module = get_component_module(component_name)
    module.install(repo=repo, release=release, format=format, arch=arch)


def configure_component(component_name: str) -> None:
    """
    Configure a component after installation.

    Args:
        component_name: Component identifier
    """
    module = get_component_module(component_name)
    if hasattr(module, "configure"):
        module.configure()


def remove_component(component_name: str) -> None:
    """
    Remove a component.

    Args:
        component_name: Component identifier
    """
    module = get_component_module(component_name)
    if hasattr(module, "remove"):
        module.remove()
