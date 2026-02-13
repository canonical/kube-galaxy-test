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

__all__ = [
    # Public API
    "HookStage",
    "register_component_class",
    "get_component_class",
    "create_component_instance",
    "get_all_component_classes",
    "install_component",
    "configure_component",
    "remove_component",
    # Component modules (imported for @register_component_class decorator side-effects)
    "cluster_autoscaler",
    "cni_plugins",
    "containerd",
    "coredns",
    "etcd",
    "etcdctl",
    "kube_apiserver",
    "kube_controller_manager",
    "kube_proxy",
    "kube_scheduler",
    "kubeadm",
    "kubectl",
    "kubelet",
    "node_problem_detector",
    "pause",
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


def install_component(
    component_name: str,
    repo: str,
    release: str,
    format: str,
    arch: str,
    manifest=None,
    component_config=None,
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
            f"Please ensure it has a ComponentBase subclass with @register_component_class decorator."
        )
    
    # Create instance with manifest context
    instance = create_component_instance(component_name, manifest, component_config)
    
    # Execute hooks in order (ComponentBase provides empty defaults for all hooks)
    instance.download_hook(repo, release, format, arch)
    instance.pre_install_hook()
    instance.install_hook(repo, release, format, arch)


def configure_component(component_name: str, manifest=None, component_config=None) -> None:
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
            f"Please ensure it has a ComponentBase subclass with @register_component_class decorator."
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
            f"Please ensure it has a ComponentBase subclass with @register_component_class decorator."
        )
    
    # Create instance and call remove hook (ComponentBase provides empty default)
    instance = create_component_instance(component_name, None, None)
    instance.remove_hook()


# Import all component modules to trigger @register_component_class decorators.
# These imports MUST be at the end to avoid circular imports.
from kube_galaxy.pkg.components import cluster_autoscaler
from kube_galaxy.pkg.components import cni_plugins
from kube_galaxy.pkg.components import containerd
from kube_galaxy.pkg.components import coredns
from kube_galaxy.pkg.components import etcd
from kube_galaxy.pkg.components import etcdctl
from kube_galaxy.pkg.components import kube_apiserver
from kube_galaxy.pkg.components import kube_controller_manager
from kube_galaxy.pkg.components import kube_proxy
from kube_galaxy.pkg.components import kube_scheduler
from kube_galaxy.pkg.components import kubeadm
from kube_galaxy.pkg.components import kubectl
from kube_galaxy.pkg.components import kubelet
from kube_galaxy.pkg.components import node_problem_detector
from kube_galaxy.pkg.components import pause
from kube_galaxy.pkg.components import runc
