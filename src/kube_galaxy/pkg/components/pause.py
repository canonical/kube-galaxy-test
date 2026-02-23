"""
Pause component installation and management.

The pause container is used for infrastructure.
"""

from kube_galaxy.pkg.components import ComponentBase, register_component


@register_component("pause")
class Pause(ComponentBase):
    """
    Pause component for Kubernetes infrastructure.

    This component handles the pause container deployment.
    """
