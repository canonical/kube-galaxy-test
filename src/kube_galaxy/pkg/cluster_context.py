"""Shared runtime context for cluster orchestration and component hooks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from kube_galaxy.pkg.manifest.models import NodeRole
from kube_galaxy.pkg.units._base import Unit

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase
    from kube_galaxy.pkg.utils.artifact_server import ArtifactServer
    from kube_galaxy.pkg.utils.registry_mirror import RegistryMirror

__all__ = ["ClusterContext"]

UnitKey = tuple[NodeRole, int]


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
    _units: dict[UnitKey, Unit] = field(default_factory=dict)

    @property
    def units(self) -> dict[UnitKey, Unit]:
        """Lookup dict for all Units in the cluster, keyed by (role, index)."""
        return self._units

    @units.setter
    def units(self, value: Iterable[Unit]) -> None:
        """Set the list of Units in the cluster, indexed by (role, index)."""
        self._units = {(unit.role, unit.index): unit for unit in value}

    @property
    def control_plane_units(self) -> dict[int, Unit]:
        """Lookup dict for control-plane Units, keyed by index."""
        return {
            index: unit
            for (role, index), unit in self._units.items()
            if role == NodeRole.CONTROL_PLANE
        }

    @property
    def worker_units(self) -> dict[int, Unit]:
        """Lookup dict for worker Units, keyed by index."""
        return {
            index: unit for (role, index), unit in self._units.items() if role == NodeRole.WORKER
        }
