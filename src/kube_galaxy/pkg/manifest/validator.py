"""Manifest validation and utilities."""

from pathlib import Path
from typing import Any

import yaml

from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import ComponentConfig, Manifest


def task_path_for_component(component: ComponentConfig) -> Path:
    """Get the expected path to the component's test task definition.

    For components with a local repo source, the task definition is looked up
    directly from the local path (``<local>/spread/kube-galaxy/``).  For remote
    sources the task definition lives under the shared tests root.
    """
    if component.repo.is_local and component.repo.local is not None:
        return component.repo.local / "spread/kube-galaxy/"
    return SystemPaths.tests_root() / component.name / "spread/kube-galaxy/"


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

    if not component.test:
        return errors  # No validation needed for components without tests

    # Validate task yaml is valid YAML and has required fields (name, execute)
    task_path = task_path_for_component(component) / "task.yaml"
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
    """Get all components marked with test=true that have a spread test suite defined.

    Args:
        manifest: Manifest to query

    Returns:
        List of component configs with runnable tests
    """

    def has_spread_test(comp: ComponentConfig) -> bool:
        path_to_tasks = task_path_for_component(comp)
        return comp.test and path_to_tasks.exists() and any(path_to_tasks.glob("task.yaml"))

    return [comp for comp in manifest.components if has_spread_test(comp)]
