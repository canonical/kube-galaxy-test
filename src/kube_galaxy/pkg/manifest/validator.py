"""Manifest validation and utilities."""

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


def get_components_with_spread(manifest: Manifest) -> list[ComponentConfig]:
    """Get all components marked with use_spread=true.

    Args:
        manifest: Manifest to query

    Returns:
        List of component configs with spread tests enabled
    """
    return [comp for comp in manifest.components if comp.use_spread]


def get_component(manifest: Manifest, name: str) -> ComponentConfig | None:
    """Get component config by name from manifest.

    Args:
        manifest: Manifest to search
        name: Component config name

    Returns:
        ComponentConfig if found, None otherwise
    """
    return manifest.get_component(name)
