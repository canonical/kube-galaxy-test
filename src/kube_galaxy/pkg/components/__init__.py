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
    # Get class-based component (already registered via imports at top of module)
    component_class = get_component_class(component_name)
    if not component_class:
        raise AttributeError(
            f"Component '{component_name}' not found. "
            f"Please ensure it has a ComponentBase subclass with @register_component_class decorator."
        )
    
    # Create instance with manifest context
    instance = create_component_instance(component_class, manifest, component_config)
    
    # Execute hooks in order
    if hasattr(instance, 'download_hook'):
        instance.download_hook(repo, release, format, arch)
    if hasattr(instance, 'pre_install_hook'):
        instance.pre_install_hook()
    if hasattr(instance, 'install_hook'):
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
    # Get class-based component (already registered via imports at top of module)
    component_class = get_component_class(component_name)
    if not component_class:
        raise AttributeError(
            f"Component '{component_name}' not found. "
            f"Please ensure it has a ComponentBase subclass with @register_component_class decorator."
        )
    
    # Create instance with manifest context
    instance = create_component_instance(component_class, manifest, component_config)
    
    # Execute configuration hooks
    if hasattr(instance, 'bootstrap_hook'):
        instance.bootstrap_hook()
    if hasattr(instance, 'post_bootstrap_hook'):
        instance.post_bootstrap_hook()
    if hasattr(instance, 'configure_hook'):
        instance.configure_hook()


def remove_component(component_name: str) -> None:
    """
    Remove a component.

    Args:
        component_name: Component identifier
    
    Raises:
        AttributeError: If component class not found
    """
    # Get class-based component (already registered via imports at top of module)
    component_class = get_component_class(component_name)
    if not component_class:
        raise AttributeError(
            f"Component '{component_name}' not found. "
            f"Please ensure it has a ComponentBase subclass with @register_component_class decorator."
        )
    
    # Create instance and call remove hook if it exists
    instance = create_component_instance(component_class, None, None)
    if hasattr(instance, 'remove_hook'):
        instance.remove_hook()


# Import all component modules to trigger @register_component_class decorators.
# These imports MUST be at the end to avoid circular imports:
# - Component modules import register_component_class from this file
# - This file needs to define register_component_class first
# - Then we can import the component modules
# The noqa: F401 tells linters these imports are intentional (side-effect imports for decorator execution)
from kube_galaxy.pkg.components import cluster_autoscaler  # noqa: F401
from kube_galaxy.pkg.components import cni_plugins  # noqa: F401
from kube_galaxy.pkg.components import containerd  # noqa: F401
from kube_galaxy.pkg.components import coredns  # noqa: F401
from kube_galaxy.pkg.components import etcd  # noqa: F401
from kube_galaxy.pkg.components import etcdctl  # noqa: F401
from kube_galaxy.pkg.components import kube_apiserver  # noqa: F401
from kube_galaxy.pkg.components import kube_controller_manager  # noqa: F401
from kube_galaxy.pkg.components import kube_proxy  # noqa: F401
from kube_galaxy.pkg.components import kube_scheduler  # noqa: F401
from kube_galaxy.pkg.components import kubeadm  # noqa: F401
from kube_galaxy.pkg.components import kubectl  # noqa: F401
from kube_galaxy.pkg.components import kubelet  # noqa: F401
from kube_galaxy.pkg.components import node_problem_detector  # noqa: F401
from kube_galaxy.pkg.components import pause  # noqa: F401
from kube_galaxy.pkg.components import runc  # noqa: F401
