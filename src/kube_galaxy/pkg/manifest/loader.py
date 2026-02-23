"""YAML manifest loader for kube-galaxy."""

from pathlib import Path
from typing import Any

import yaml

from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    NetworkConfig,
)


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

    data: dict[str, Any] = yaml.safe_load(manifest_path.open())

    if not isinstance(data, dict):
        raise ValueError("Manifest must be a YAML dictionary")

    return _deserialize_manifest(data, manifest_path)


def _deserialize_manifest(data: dict[str, Any], path: Path) -> Manifest:
    """Deserialize manifest dictionary to Manifest dataclass."""
    # Parse components
    components: list[ComponentConfig] = []
    for comp_data in data.get("components", []):
        install_data = comp_data.get("installation", {})
        installation = InstallConfig(
            method=InstallMethod(install_data.get("method", "binary-archive")),
            source_format=install_data.get("source_format", ""),
        )
        component = ComponentConfig(
            name=comp_data["name"],
            category=comp_data.get("category", ""),
            release=comp_data["release"],
            repo=comp_data["repo"],
            installation=installation,
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
        path=path,
        description=data.get("description", ""),
        kubernetes_version=data["kubernetes-version"],
        components=components,
        networking=networking,
    )
