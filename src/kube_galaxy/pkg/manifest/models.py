"""Manifest data models for kube-galaxy."""

from dataclasses import dataclass, field


@dataclass
class Component:
    """Kubernetes component specification."""

    name: str
    category: str
    release: str
    repo: str
    format: str  # Binary, Container, or Binary+Container (legacy, kept for compatibility)
    use_spread: bool = False

    # Component lifecycle configuration
    dependencies: list[str] = field(default_factory=list)  # Must install after these components
    priority: int = 50  # Lower = earlier (for components without dependencies)

    # Installation method configuration
    install_method: str | None = (
        None  # e.g., "binary-archive", "binary-direct", "helm-chart", "pod-manifest"
    )
    archive_format: str | None = None  # e.g., "tar.gz", "tar.xz" (for binary-archive method)

    # Custom binary/image URLs (optional, overrides default repo/release)
    custom_binary_url: str | None = None
    custom_image_url: str | None = None

    # Helm chart specific configuration
    helm_chart_url: str | None = None
    helm_values: dict = field(default_factory=dict)

    # Manifest specific configuration
    manifest_url: str | None = None
    manifest_type: str | None = None  # "pod", "deployment", "daemonset", etc.

    # Hook configuration overrides
    skip_hooks: list[str] = field(default_factory=list)  # Hooks to skip (e.g., ["bootstrap"])
    hook_config: dict = field(default_factory=dict)  # Hook-specific configuration


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
    components: list[Component] = field(default_factory=list)
    networking: list[NetworkConfig] = field(default_factory=list)

    def get_component(self, name: str) -> Component | None:
        """Get component by name."""
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

    def get_components_by_priority(self) -> list[Component]:
        """
        Get components sorted by priority and dependencies.

        Returns components in installation order considering:
        1. Priority (lower = earlier)
        2. Dependencies (dependencies must come before dependents)

        Returns:
            List of components in execution order
        """
        # Simple topological sort based on dependencies and priority
        sorted_components = []
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
