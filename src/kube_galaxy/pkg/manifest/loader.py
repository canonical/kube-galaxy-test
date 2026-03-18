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
    RepoInfo,
    TestConfig,
    TestMethod,
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


def _parse_repo(repo_data: Any, comp_name: str) -> RepoInfo:
    """Parse a ``repo`` block from a YAML dict.

    Args:
        repo_data: The raw value of a ``repo`` key in the manifest.
        comp_name: Component name used in error messages.

    Returns:
        A populated :class:`RepoInfo` instance.

    Raises:
        ValueError: When ``repo_data`` is not a recognised format.
    """
    if repo_data is None:
        return RepoInfo()
    if isinstance(repo_data, dict) and (base_url := repo_data.get("base-url")):
        return RepoInfo(
            base_url=base_url,
            subdir=repo_data.get("subdir"),
            ref=repo_data.get("ref"),
        )
    raise ValueError(
        f"Component {comp_name}: 'repo' must be an object with 'base-url' field, got: {repo_data!r}"
    )


def _parse_environment(env_data: Any, comp_name: str) -> dict[str, str]:
    """Parse a ``test.environment`` block from a YAML value.

    Args:
        env_data: The raw value of an ``environment`` key in the manifest.
        comp_name: Component name used in error messages.

    Returns:
        A ``dict[str, str]`` of environment variable names to values.
        ``None`` is treated as an empty dict.

    Raises:
        ValueError: When ``env_data`` is not a mapping, or contains non-string
            keys or values.
    """
    if env_data is None:
        return {}
    if not isinstance(env_data, dict):
        raise ValueError(
            f"Component {comp_name}: 'test.environment' must be a mapping, "
            f"got: {type(env_data).__name__}"
        )
    result: dict[str, str] = {}
    for key, value in env_data.items():
        if not isinstance(key, str):
            raise ValueError(
                f"Component {comp_name}: 'test.environment' key must be a string, got: {key!r}"
            )
        if not isinstance(value, str):
            raise ValueError(
                f"Component {comp_name}: 'test.environment' value for key {key!r} "
                f"must be a string, got: {value!r}"
            )
        result[key] = value
    return result


def _deserialize_manifest(data: dict[str, Any], path: Path) -> Manifest:
    """Deserialize manifest dictionary to Manifest dataclass."""
    # Parse components
    components: list[ComponentConfig] = []
    for comp_data in data.get("components", []):
        comp_name = comp_data.get("name", "")

        # Parse installation block (repo lives inside installation)
        install_data = comp_data.get("installation", {})
        installation = InstallConfig(
            method=InstallMethod(install_data.get("method", "none")),
            source_format=install_data.get("source-format", ""),
            bin_path=install_data.get("bin-path", "./*"),
            repo=_parse_repo(install_data.get("repo"), comp_name),
        )

        # Parse test block (mirrors install config; absent / false → method: none)
        test_data = comp_data.get("test", {})
        test_config = TestConfig(
            method=TestMethod(test_data.get("method", "none")),
            source_format=test_data.get("source-format", ""),
            repo=_parse_repo(test_data.get("repo"), comp_name),
            environment=_parse_environment(test_data.get("environment"), comp_name),
        )

        component = ComponentConfig(
            name=comp_data["name"],
            category=comp_data.get("category", ""),
            release=comp_data["release"],
            installation=installation,
            test=test_config,
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
