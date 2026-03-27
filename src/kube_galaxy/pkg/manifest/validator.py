"""Manifest validation and utilities."""

from typing import Any

import yaml

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import ComponentConfig, Manifest, TestMethod

_VALID_PROVIDER_TYPES = {"local", "lxd", "multipass", "ssh"}
_VALID_PLACEMENT_VALUES = {"all", "control-plane", "workers", "orchestrator"}


def validate_manifest(manifest: Manifest) -> None:
    """Validate manifest structure and required fields.

    Args:
        manifest: Manifest to validate

    Raises:
        ValueError: If manifest is invalid
    """
    if not manifest.name:
        raise ValueError("Manifest must have a 'name' field")

    if not manifest.kubernetes_version:
        raise ValueError("Manifest must have a 'kubernetes-version' field")

    # Validate provider block
    provider_type = manifest.provider.type
    if provider_type not in _VALID_PROVIDER_TYPES:
        raise ValueError(
            f"Invalid provider type '{provider_type}'. "
            f"Must be one of: {', '.join(sorted(_VALID_PROVIDER_TYPES))}"
        )

    if provider_type == "ssh" and not manifest.provider.hosts:
        raise ValueError("Provider type 'ssh' requires at least one host in 'provider.hosts'")

    # Validate provider.nodes block
    if manifest.provider.nodes.control_plane < 1:
        raise ValueError("'provider.nodes.control-plane' must be at least 1")

    if manifest.provider.nodes.worker < 0:
        raise ValueError("'provider.nodes.worker' must be non-negative")

    # Validate artifact.registry block
    registry = manifest.artifact.registry
    if registry.enabled and not (1 <= registry.port <= 65535):
        raise ValueError(
            f"'artifact.registry.port' must be between 1 and 65535, got {registry.port}"
        )


def validate_component_test_structure(component: ComponentConfig) -> list[str]:
    """Validate component has proper structure for spread tests.

    Args:
        component: Component to validate

    Returns:
        List of validation errors (empty if valid)

    Note:
        Full validation (checking if repo exists, has correct directory structure)
        requires cloning the repo, which is expensive. This function performs
        basic checks only. Deep validation happens during test execution.
    """
    errors: list[str] = []

    if component.test.method != TestMethod.SPREAD:
        return errors  # No validation needed for components without spread tests

    # Validate task yaml is valid YAML and has required fields (name, execute)
    task_path = SystemPaths.tests_component_root(component.name) / "task.yaml"
    content: dict[str, Any] = {}
    if not task_path.exists():
        errors.append(
            f"Component '{component.name}' is marked for testing "
            f"but task.yaml not found at {task_path}"
        )
        return errors

    try:
        content = yaml.safe_load(task_path.read_text()) or {}  # Will raise if not valid YAML
    except yaml.YAMLError as e:
        errors.append(f"Component '{component.name}' has invalid YAML in task.yaml: {e}")

    if "execute" not in content:
        errors.append(f"Component '{component.name}' task.yaml missing 'execute' field")

    return errors


def get_components_with_spread(manifest: Manifest) -> list[ComponentConfig]:
    """Get all components with a spread test suite defined.

    Args:
        manifest: Manifest to query

    Returns:
        List of component configs with runnable spread tests
    """

    def has_spread_test(comp: ComponentConfig) -> bool:
        if comp.test.method != TestMethod.SPREAD:
            return False
        path_to_tasks = SystemPaths.tests_component_root(comp.name)
        return path_to_tasks.exists() and any(path_to_tasks.glob("task.yaml"))

    return [comp for comp in manifest.components if has_spread_test(comp)]
