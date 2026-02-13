"""YAML manifest loader for kube-galaxy."""

from pathlib import Path
from typing import Any

import yaml

from kube_galaxy.pkg.manifest.models import Component, Manifest, NetworkConfig, NodeConfig


def load_manifest(path: str | Path) -> Manifest:
    """Load and parse a manifest YAML file.

    Args:
        path: Path to manifest YAML file

    Returns:
        Manifest dataclass instance

    Raises:
        FileNotFoundError: If manifest file does not exist
        yaml.YAMLError: If YAML is invalid
        ValueError: If manifest structure is invalid
    """
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    with open(manifest_path) as f:
        data: dict[str, Any] = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Manifest must be a YAML dictionary")

    return _deserialize_manifest(data)


def _deserialize_manifest(data: dict[str, Any]) -> Manifest:
    """Deserialize manifest dictionary to Manifest dataclass."""
    # Parse nodes
    nodes_data = data.get("nodes", {})
    nodes = NodeConfig(
        control_plane=nodes_data.get("control-plane", 1),
        worker=nodes_data.get("worker", 1),
    )

    # Parse components
    components: list[Component] = []
    for comp_data in data.get("components", []):
        component = Component(
            name=comp_data["name"],
            category=comp_data.get("category", ""),
            release=comp_data["release"],
            repo=comp_data["repo"],
            format=comp_data.get("format", "Binary"),
            use_spread=comp_data.get("use-spread", False),
        )
        components.append(component)

    # Parse networking
    networking: list[NetworkConfig] = []
    for net_data in data.get("networking", []):
        net_config = NetworkConfig(
            name=net_data.get("name", "default"),
            service_cidr=net_data.get("service-cidr", "10.96.0.0/12"),
            pod_cidr=net_data.get("pod-cidr", "192.168.0.0/16"),
        )
        networking.append(net_config)

    return Manifest(
        name=data["name"],
        description=data.get("description", ""),
        kubernetes_version=data["kubernetes-version"],
        nodes=nodes,
        components=components,
        networking=networking,
    )
