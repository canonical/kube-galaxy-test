"""Manifest data models for kube-galaxy."""

from dataclasses import dataclass, field


@dataclass
class Component:
    """Kubernetes component specification."""

    name: str
    category: str
    release: str
    repo: str
    format: str  # Binary, Container, or Binary+Container
    use_spread: bool = False


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
