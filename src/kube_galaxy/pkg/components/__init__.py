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
"""

import importlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


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
    
    def has_hook(self, stage: HookStage) -> bool:
        """Check if component has a specific hook."""
        hook_attr = stage.value
        return getattr(self, hook_attr, None) is not None
    
    def get_hook(self, stage: HookStage) -> Optional[Callable]:
        """Get the hook function for a stage."""
        hook_attr = stage.value
        return getattr(self, hook_attr, None)


# Registry of component hooks
_COMPONENT_HOOKS: dict[str, ComponentHooks] = {}


def register_component_hooks(hooks: ComponentHooks) -> None:
    """
    Register hooks for a component.
    
    Args:
        hooks: ComponentHooks instance defining the component's lifecycle
    """
    _COMPONENT_HOOKS[hooks.name] = hooks


def get_component_hooks(component_name: str) -> Optional[ComponentHooks]:
    """
    Get registered hooks for a component.
    
    Args:
        component_name: Component identifier
        
    Returns:
        ComponentHooks if registered, None otherwise
    """
    return _COMPONENT_HOOKS.get(component_name)


def get_all_component_hooks() -> dict[str, ComponentHooks]:
    """Get all registered component hooks."""
    return _COMPONENT_HOOKS.copy()


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

