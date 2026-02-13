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
from kube_galaxy.pkg.components.containerd import Containerd
from kube_galaxy.pkg.components.kubeadm import Kubeadm

__all__ = [
    "ComponentBase",
    "COMPONENTS",
    "HookStage",
    "configure_component",
    "get_component_class",
    "install_component",
    "remove_component",
]


class HookStage(Enum):
    """Component lifecycle stages."""

    DOWNLOAD = "download"
    PRE_INSTALL = "pre_install"
    INSTALL = "install"
    BOOTSTRAP = "bootstrap"
    POST_BOOTSTRAP = "post_bootstrap"
    CONFIGURE = "configure"


# Simple mapping of component names to classes
COMPONENTS: dict[str, type[ComponentBase]] = {
    "containerd": Containerd,
    "kubeadm": Kubeadm,
}


def get_component_class(component_name: str) -> type[ComponentBase] | None:
    """
    Get component class by name.

    Args:
        component_name: Component identifier

    Returns:
        Component class if found, None otherwise
    """
    return COMPONENTS.get(component_name)


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
        raise AttributeError(f"Component '{component_name}' not found in COMPONENTS registry.")

    # Create instance with manifest context
    instance = component_class(manifest, component_config)

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
        raise AttributeError(f"Component '{component_name}' not found in COMPONENTS registry.")

    # Create instance with manifest context
    instance = component_class(manifest, component_config)

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
        raise AttributeError(f"Component '{component_name}' not found in COMPONENTS registry.")

    # Create instance and call remove hook (ComponentBase provides empty default)
    instance = component_class(None, None)
    instance.remove_hook()
