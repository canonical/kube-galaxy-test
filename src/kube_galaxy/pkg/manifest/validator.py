"""Manifest validation and utilities."""

from git import cmd as git_cmd

from kube_galaxy.pkg.manifest.models import ComponentConfig, Manifest


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

    # Check required fields
    if not component.repo.base_url:
        errors.append(
            f"Component {component.name}: 'repo.base-url' field is required for spread tests"
        )

    try:
        # Use git ls-remote to check if repo exists and is accessible
        # This is fast and doesn't clone the repo
        git = git_cmd.Git()
        git.ls_remote(component.repo.base_url, heads=True)
    except Exception as exc:
        errors.append(
            f"Component {component.name}: cannot access repo at '{component.repo.base_url}' - {exc}"
        )

    # Validate subdir doesn't start with / or contain ..
    if component.repo.subdir:
        if component.repo.subdir.startswith("/") or ".." in component.repo.subdir:
            errors.append(
                f"Component {component.name}: invalid 'repo.subdir' '{component.repo.subdir}' "
                "(must be relative path without '..')"
            )

    return errors


def get_components_with_spread(manifest: Manifest) -> list[ComponentConfig]:
    """Get all components marked with test=true.

    Args:
        manifest: Manifest to query

    Returns:
        List of component configs with tests enabled
    """
    return [comp for comp in manifest.components if comp.test]


def get_component(manifest: Manifest, name: str) -> ComponentConfig | None:
    """Get component config by name from manifest.

    Args:
        manifest: Manifest to search
        name: Component config name

    Returns:
        ComponentConfig if found, None otherwise
    """
    return manifest.get_component(name)
