"""
Component installation and management modules.

Each component in the Kubernetes cluster has its own module with:
- install(): Download and install the component
- configure(): Post-install configuration
- remove(): Cleanup and removal

Component Lifecycle Hooks:
- download: Download binaries/containers (parallel with pooling)
- pre_install: Machine preparation (swapoff, sysctl, etc.)
- install: Install component binaries/configs
- bootstrap: Initialize services (e.g., kubeadm init)
- post_bootstrap: Post-initialization tasks (e.g., get kubeconfig)
- configure: Final configuration and verification

New in v2: Class-based components inherit from ComponentBase
"""

import importlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Type

from kube_galaxy.pkg.components.constants import (
    DEFAULT_BOOTSTRAP_TIMEOUT,
    DEFAULT_CONFIGURE_TIMEOUT,
    DEFAULT_DOWNLOAD_TIMEOUT,
    DEFAULT_INSTALL_TIMEOUT,
    DEFAULT_POST_BOOTSTRAP_TIMEOUT,
    DEFAULT_PRE_INSTALL_TIMEOUT,
)


class HookStage(Enum):
    """Component lifecycle stages."""
    
    DOWNLOAD = "download"
    PRE_INSTALL = "pre_install"
    INSTALL = "install"
    BOOTSTRAP = "bootstrap"
    POST_BOOTSTRAP = "post_bootstrap"
    CONFIGURE = "configure"


@dataclass
class ComponentHooks:
    """
    Defines the lifecycle hooks for a component.
    
    Each hook is an optional callable that takes standard arguments.
    Components can define only the hooks they need.
    
    Hook Execution Order:
    1. download - Download binaries/containers (can run in parallel)
    2. pre_install - Prepare machine for installation
    3. install - Install the component
    4. bootstrap - Initialize/start the component
    5. post_bootstrap - Post-initialization tasks
    6. configure - Final configuration
    
    Timeout Configuration:
    Each component can define custom timeouts for each stage.
    If not specified, defaults from constants.py are used.
    
    Note: This class is being phased out in favor of ComponentBase.
    New components should inherit from ComponentBase instead.
    """
    
    # Component metadata
    name: str
    category: str
    
    # Hook functions (all optional)
    download: Optional[Callable] = None
    pre_install: Optional[Callable] = None
    install: Optional[Callable] = None
    bootstrap: Optional[Callable] = None
    post_bootstrap: Optional[Callable] = None
    configure: Optional[Callable] = None
    
    # Component dependencies (must complete before this component)
    dependencies: list[str] = field(default_factory=list)
    
    # Execution priority (lower = earlier, default = 50)
    priority: int = 50
    
    # Timeout configuration (in seconds) for each stage
    # None means use default from constants
    download_timeout: Optional[int] = None
    pre_install_timeout: Optional[int] = None
    install_timeout: Optional[int] = None
    bootstrap_timeout: Optional[int] = None
    post_bootstrap_timeout: Optional[int] = None
    configure_timeout: Optional[int] = None
    
    def has_hook(self, stage: HookStage) -> bool:
        """Check if component has a specific hook."""
        hook_attr = stage.value
        return getattr(self, hook_attr, None) is not None
    
    def get_hook(self, stage: HookStage) -> Optional[Callable]:
        """Get the hook function for a stage."""
        hook_attr = stage.value
        return getattr(self, hook_attr, None)
    
    def get_timeout(self, stage: HookStage) -> int:
        """
        Get timeout for a specific stage.
        
        Returns component-specific timeout if set, otherwise default.
        
        Args:
            stage: The lifecycle stage
            
        Returns:
            Timeout in seconds
        """
        timeout_attr = f"{stage.value}_timeout"
        component_timeout = getattr(self, timeout_attr, None)
        
        if component_timeout is not None:
            return component_timeout
        
        # Return default timeout for the stage
        defaults = {
            HookStage.DOWNLOAD: DEFAULT_DOWNLOAD_TIMEOUT,
            HookStage.PRE_INSTALL: DEFAULT_PRE_INSTALL_TIMEOUT,
            HookStage.INSTALL: DEFAULT_INSTALL_TIMEOUT,
            HookStage.BOOTSTRAP: DEFAULT_BOOTSTRAP_TIMEOUT,
            HookStage.POST_BOOTSTRAP: DEFAULT_POST_BOOTSTRAP_TIMEOUT,
            HookStage.CONFIGURE: DEFAULT_CONFIGURE_TIMEOUT,
        }
        
        return defaults.get(stage, 60)  # Fallback to 60s if stage not found


# Registry of component hooks (function-based, legacy)
_COMPONENT_HOOKS: dict[str, ComponentHooks] = {}

# Registry of component classes (class-based, new)
_COMPONENT_CLASSES: dict[str, Type] = {}


def register_component_hooks(hooks: ComponentHooks) -> None:
    """
    Register hooks for a component (legacy function-based).
    
    Args:
        hooks: ComponentHooks instance defining the component's lifecycle
        
    Note: This is the legacy registration method. New components should
    use register_component_class instead.
    """
    _COMPONENT_HOOKS[hooks.name] = hooks


def register_component_class(component_class: Type) -> None:
    """
    Register a component class (new class-based approach).
    
    Args:
        component_class: Class that inherits from ComponentBase
        
    Example:
        @register_component_class
        class KubeadmComponent(ComponentBase):
            COMPONENT_NAME = "kubeadm"
            ...
    """
    if not hasattr(component_class, 'COMPONENT_NAME'):
        raise ValueError(f"Component class {component_class} must define COMPONENT_NAME")
    
    _COMPONENT_CLASSES[component_class.COMPONENT_NAME] = component_class
    return component_class


def get_component_hooks(component_name: str) -> Optional[ComponentHooks]:
    """
    Get registered hooks for a component (legacy function-based).
    
    Args:
        component_name: Component identifier
        
    Returns:
        ComponentHooks if registered, None otherwise
    """
    return _COMPONENT_HOOKS.get(component_name)


def get_component_class(component_name: str) -> Optional[Type]:
    """
    Get registered class for a component (new class-based).
    
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


def get_all_component_hooks() -> dict[str, ComponentHooks]:
    """Get all registered component hooks (legacy)."""
    return _COMPONENT_HOOKS.copy()


def get_all_component_classes() -> dict[str, Type]:
    """Get all registered component classes (new)."""
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

