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

from enum import Enum
from typing import Any

from kube_galaxy.pkg.components._base import ComponentBase

__all__ = [
    # Public API
    "HookStage",
    "cluster_autoscaler",
    "cni_plugins",
    "configure_component",
    "containerd",
    "coredns",
    "create_component_instance",
    "etcd",
    "etcdctl",
    "get_all_component_classes",
    "get_component_class",
    "install_component",
    "kube_apiserver",
    "kube_controller_manager",
    "kube_proxy",
    "kube_scheduler",
    "kubeadm",
    "kubectl",
    "kubelet",
    "node_problem_detector",
    "pause",
    "register_component_class",
    "remove_component",
    "runc",
]


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


def register_component_class(component_class: type[ComponentBase]) -> type[ComponentBase]:
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


def create_component_instance(
    component_name: str, manifest: Any, component: Any
) -> ComponentBase:
    """
    Create an instance of a component with manifest context.

    Args:
        component_name: Component identifier
        manifest: Full Manifest object
        component: Component configuration object

    Returns:
        Component instance

    Raises:
        AttributeError: If component not found
    """
    component_class = get_component_class(component_name)
    if not component_class:
        raise AttributeError(f"Component '{component_name}' not found.")
    return component_class(manifest, component)  # type: ignore[no-any-return]


def get_all_component_classes() -> dict[str, type]:
    """Get all registered component classes."""
    return _COMPONENT_CLASSES.copy()


def install_component(
    component_name: str,
    repo: str,
    release: str,
    format: str,
    arch: str,
    manifest: Any = None,
    component_config: Any = None,
) -> None:
    """
    Install a component using the class-based interface.

    Args:
        component_name: Component identifier
        repo: Repository URL
        release: Release/version tag
        format: Installation format (Binary, Container, Binary+Container)
        arch: Architecture (amd64, arm64, etc.)
        manifest: Optional manifest object for context
        component_config: Optional component configuration

    Raises:
        AttributeError: If component class not found
    """
    component_class = get_component_class(component_name)
    if not component_class:
        raise AttributeError(
            f"Component '{component_name}' not found. "
            f"Please ensure it has a ComponentBase subclass with "
            f"@register_component_class decorator."
        )

    # Create instance with manifest context
    instance = create_component_instance(component_name, manifest, component_config)

    # Execute hooks in order (ComponentBase provides empty defaults for all hooks)
    instance.download_hook(repo, release, format, arch)
    instance.pre_install_hook()
    instance.install_hook(repo, release, format, arch)


def configure_component(
    component_name: str, manifest: Any = None, component_config: Any = None
) -> None:
    """
    Configure a component after installation using the class-based interface.

    Args:
        component_name: Component identifier
        manifest: Optional manifest object for context
        component_config: Optional component configuration

    Raises:
        AttributeError: If component class not found
    """
    component_class = get_component_class(component_name)
    if not component_class:
        raise AttributeError(
            f"Component '{component_name}' not found. "
            f"Please ensure it has a ComponentBase subclass with "
            f"@register_component_class decorator."
        )

    # Create instance with manifest context
    instance = create_component_instance(component_name, manifest, component_config)

    # Execute configuration hooks (ComponentBase provides empty defaults for all hooks)
    instance.bootstrap_hook()
    instance.post_bootstrap_hook()
    instance.configure_hook()


def remove_component(component_name: str) -> None:
    """
    Remove a component.

    Args:
        component_name: Component identifier

    Raises:
        AttributeError: If component class not found
    """
    component_class = get_component_class(component_name)
    if not component_class:
        raise AttributeError(
            f"Component '{component_name}' not found. "
            f"Please ensure it has a ComponentBase subclass with "
            f"@register_component_class decorator."
        )

    # Create instance and call remove hook (ComponentBase provides empty default)
    instance = create_component_instance(component_name, None, None)
    instance.remove_hook()


# Import all component modules to trigger @register_component_class decorators.
# These imports MUST be at the end to avoid circular imports.
# ruff: noqa: E402
from kube_galaxy.pkg.components import (
    cluster_autoscaler,
    cni_plugins,
    containerd,
    coredns,
    etcd,
    etcdctl,
    kube_apiserver,
    kube_controller_manager,
    kube_proxy,
    kube_scheduler,
    kubeadm,
    kubectl,
    kubelet,
    node_problem_detector,
    pause,
    runc,
)
