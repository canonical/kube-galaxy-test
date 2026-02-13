"""
Component installation and management modules.

Components inherit from ComponentBase and override the lifecycle hooks they need.

Component Lifecycle Hooks (8 stages):
1. download: Download binaries/containers (parallel with pooling)
2. pre_install: Machine preparation (swapoff, sysctl, etc.)
3. install: Install component binaries/configs
4. configure: Configure component (config files, settings)
5. bootstrap: Initialize services (e.g., kubeadm init)
6. post_bootstrap: Post-initialization tasks (e.g., get kubeconfig)
7. verify: Verify component is working
8. test: Run component tests (optional)
"""

from enum import Enum
from typing import Any

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.components.containerd import Containerd
from kube_galaxy.pkg.components.kubeadm import Kubeadm

__all__ = [
    "COMPONENTS",
    "ComponentBase",
    "HookStage",
    "configure_component",
    "install_component",
    "remove_component",
]


class HookStage(Enum):
    """Component lifecycle stages."""

    DOWNLOAD = "download"
    PRE_INSTALL = "pre_install"
    INSTALL = "install"
    CONFIGURE = "configure"
    BOOTSTRAP = "bootstrap"
    POST_BOOTSTRAP = "post_bootstrap"
    VERIFY = "verify"
    TEST = "test"


# Simple mapping of component names to classes
COMPONENTS: dict[str, type[ComponentBase]] = {
    "containerd": Containerd,
    "kubeadm": Kubeadm,
}


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
        KeyError: If component not found in COMPONENTS
    """
    component_class = COMPONENTS[component_name]
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
        KeyError: If component not found in COMPONENTS
    """
    component_class = COMPONENTS[component_name]
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
        KeyError: If component not found in COMPONENTS
    """
    component_class = COMPONENTS[component_name]
    instance = component_class(None, None)
    instance.remove_hook()
