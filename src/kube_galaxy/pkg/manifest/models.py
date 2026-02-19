"""Manifest data models for kube-galaxy."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class InstallMethod(StrEnum):
    """Installation method for components."""

    BINARY = "binary"  # Direct binary download and install
    BINARY_ARCHIVE = "binary-archive"  # Binary in tar/zip/xz archive from releases
    CONTAINER_IMAGE = "container-image"  # Container image from registry
    NONE = "none"  # No installation, component has no installable artifacts


@dataclass
class InstallConfig:
    """Kubernetes component installation configuration."""

    method: InstallMethod  # Installation method
    source_format: str  # e.g., format string URL or path to binary, chart, or manifest


@dataclass
class ComponentConfig:
    """Kubernetes component configuration from manifest YAML."""

    name: str
    category: str
    release: str
    repo: str
    installation: InstallConfig
    use_spread: bool = False

    # Component lifecycle configuration
    dependencies: list[str] = field(default_factory=list)  # Must install after these components

    # Hook configuration overrides
    skip_hooks: list[str] = field(default_factory=list)  # Hooks to skip (e.g., ["bootstrap"])
    hook_config: dict[str, Any] = field(default_factory=dict)  # Hook-specific configuration


@dataclass
class NetworkConfig:
    """Network configuration for cluster."""

    name: str
    service_cidr: str
    pod_cidr: str


@dataclass
class NodeConfig:
    """Node count configuration."""

    control_plane: int = 1
    worker: int = 1


@dataclass
class Manifest:
    """Cluster manifest configuration."""

    name: str
    description: str
    kubernetes_version: str
    nodes: NodeConfig
    components: list[ComponentConfig] = field(default_factory=list)
    networking: list[NetworkConfig] = field(default_factory=list)

    def get_component(self, name: str) -> ComponentConfig | None:
        """Get component config by name."""
        for component in self.components:
            if component.name == name:
                return component
        return None

    def get_networking(self, name: str = "default") -> NetworkConfig | None:
        """Get network config by name."""
        for net in self.networking:
            if net.name == name:
                return net
        return self.networking[0] if self.networking else None
