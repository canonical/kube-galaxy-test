"""Manifest data models for kube-galaxy."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class InstallMethod(StrEnum):
    """Installation method for components."""

    BINARY_ARCHIVE = "binary-archive"  # Binary in tar/zip/xz archive from releases
    CONTAINER_IMAGE = "container-image"  # Container image from registry
    HELM_CHART = "helm-chart"  # Helm chart installation
    POD_MANIFEST = "pod-manifest"  # Kubernetes manifest deployment


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
    priority: int = 50  # Lower = earlier (for components without dependencies)

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

    def get_components_by_priority(self) -> list[ComponentConfig]:
        """
        Get components sorted by priority and dependencies.

        Returns components in installation order considering:
        1. Priority (lower = earlier)
        2. Dependencies (dependencies must come before dependents)

        Returns:
            List of component configs in execution order
        """
        # Simple topological sort based on dependencies and priority
        sorted_components: list[ComponentConfig] = []
        remaining = self.components.copy()

        while remaining:
            # Find components with no unmet dependencies
            ready = []
            for comp in remaining:
                deps_met = all(
                    dep in [c.name for c in sorted_components] for dep in comp.dependencies
                )
                if deps_met:
                    ready.append(comp)

            if not ready:
                # Circular dependency or invalid dependency
                raise ValueError(
                    f"Circular or invalid dependencies detected. "
                    f"Remaining components: {[c.name for c in remaining]}"
                )

            # Sort ready components by priority
            ready.sort(key=lambda c: c.priority)

            # Add to sorted list and remove from remaining
            sorted_components.extend(ready)
            for comp in ready:
                remaining.remove(comp)

        return sorted_components
