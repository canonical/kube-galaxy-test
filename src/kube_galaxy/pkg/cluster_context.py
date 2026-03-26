"""Shared runtime context for cluster orchestration and component hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase
    from kube_galaxy.pkg.utils.artifact_server import ArtifactServer
    from kube_galaxy.pkg.utils.registry_mirror import RegistryMirror

__all__ = ["ClusterContext"]


@dataclass
class ClusterContext:
    """Runtime context shared across all component hooks during cluster setup/teardown.

    Provides typed access to the active ArtifactServer and RegistryMirror
    alongside the peer-component lookup dict. All three are accessible via
    properties on ComponentBase (self.components, self.artifact_server,
    self.registry_mirror).
    """

    components: dict[str, ComponentBase] = field(default_factory=dict)
    artifact_server: ArtifactServer | None = None
    registry_mirror: RegistryMirror | None = None
