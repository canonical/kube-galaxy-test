"""
Component installation and management modules.

Each component in the Kubernetes cluster has its own module with:
- install(): Download and install the component
- configure(): Post-install configuration
- remove(): Cleanup and removal
"""

import importlib


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
