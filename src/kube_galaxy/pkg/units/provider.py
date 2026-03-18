"""UnitProvider ABC and concrete implementations for machine lifecycle management."""

from abc import ABC, abstractmethod

from kube_galaxy.pkg.manifest.models import Manifest, NodeRole, ProviderConfig
from kube_galaxy.pkg.units._base import Unit


class UnitProvider(ABC):
    """Owns the machine lifecycle  provisioning and deprovisioning."""

    @property
    @abstractmethod
    def is_ephemeral(self) -> bool:
        """True if this provider creates and destroys machines (LXD, Multipass).

        Ephemeral providers skip component-level teardown hooks and call
        ``deprovision_all()`` directly for near-instant cleanup.
        Non-ephemeral providers (SSH, local) run full teardown per-unit.
        """

    @abstractmethod
    def provision(self, role: NodeRole, index: int) -> Unit:
        """Provision (or locate) a machine for the given role and index."""

    @abstractmethod
    def deprovision(self, unit: Unit) -> None:
        """Deprovision a single unit (destroy VM or no-op for pre-existing hosts)."""

    @abstractmethod
    def deprovision_all(self) -> None:
        """Deprovision all units managed by this provider."""


class LocalUnitProvider(UnitProvider):
    """Returns a single LocalUnit; no machines are provisioned or destroyed."""

    @property
    def is_ephemeral(self) -> bool:
        return False

    def provision(self, role: NodeRole, index: int) -> Unit:
        from kube_galaxy.pkg.units.local import LocalUnit  # noqa: PLC0415

        return LocalUnit()

    def deprovision(self, unit: Unit) -> None:
        pass  # local machine is never deprovisioned

    def deprovision_all(self) -> None:
        pass


class LXDUnitProvider(UnitProvider):
    """Provisions and destroys LXD containers/VMs."""

    def __init__(self, image: str = "ubuntu:24.04") -> None:
        self._image = image
        self._units: list[Unit] = []

    @property
    def is_ephemeral(self) -> bool:
        return True

    def provision(self, role: NodeRole, index: int) -> Unit:
        import subprocess  # noqa: PLC0415

        from kube_galaxy.pkg.units.lxdvm import LXDUnit  # noqa: PLC0415
        from kube_galaxy.pkg.utils.errors import ComponentError  # noqa: PLC0415

        name = f"kube-galaxy-{role.value}-{index}"
        result = subprocess.run(
            ["lxc", "launch", self._image, name, "--vm"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(f"Failed to launch LXD VM '{name}': {result.stderr}")
        unit: Unit = LXDUnit(name)
        self._units.append(unit)
        return unit

    def deprovision(self, unit: Unit) -> None:
        import subprocess  # noqa: PLC0415

        subprocess.run(
            ["lxc", "delete", "--force", unit.name],
            capture_output=True,
            check=False,
        )
        self._units = [u for u in self._units if u.name != unit.name]

    def deprovision_all(self) -> None:
        for unit in list(self._units):
            self.deprovision(unit)


class SSHUnitProvider(UnitProvider):
    """Returns SSHUnit instances for pre-existing hosts; no-op deprovision."""

    def __init__(self, hosts: list[str]) -> None:
        self._hosts = hosts

    @property
    def is_ephemeral(self) -> bool:
        return False

    def provision(self, role: NodeRole, index: int) -> Unit:
        from kube_galaxy.pkg.units.ssh import SSHUnit  # noqa: PLC0415

        host = self._hosts[index]
        return SSHUnit(host=host, unit_name=f"{role.value}-{index}")

    def deprovision(self, unit: Unit) -> None:
        pass  # pre-existing hosts are never deprovisioned

    def deprovision_all(self) -> None:
        pass


class MultipassUnitProvider(UnitProvider):
    """Provisions and destroys Multipass VMs."""

    def __init__(self, image: str = "ubuntu:24.04") -> None:
        self._image = image
        self._units: list[Unit] = []

    @property
    def is_ephemeral(self) -> bool:
        return True

    def provision(self, role: NodeRole, index: int) -> Unit:
        import subprocess  # noqa: PLC0415

        from kube_galaxy.pkg.units.multipass import MultipassUnit  # noqa: PLC0415
        from kube_galaxy.pkg.utils.errors import ComponentError  # noqa: PLC0415

        name = f"kube-galaxy-{role.value}-{index}"
        result = subprocess.run(
            ["multipass", "launch", self._image, "--name", name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(f"Failed to launch Multipass VM '{name}': {result.stderr}")
        unit: Unit = MultipassUnit(name)
        self._units.append(unit)
        return unit

    def deprovision(self, unit: Unit) -> None:
        import subprocess  # noqa: PLC0415

        subprocess.run(
            ["multipass", "delete", "--purge", unit.name],
            capture_output=True,
            check=False,
        )
        self._units = [u for u in self._units if u.name != unit.name]

    def deprovision_all(self) -> None:
        for unit in list(self._units):
            self.deprovision(unit)


def provider_factory(manifest: Manifest) -> UnitProvider:
    """Create the appropriate ``UnitProvider`` from a manifest's ``provider`` block.

    Defaults to ``LocalUnitProvider`` when no ``provider`` block is present
    or when ``provider.type`` is ``"local"``.
    """
    cfg: ProviderConfig = manifest.provider
    match cfg.type:
        case "local":
            return LocalUnitProvider()
        case "lxd":
            return LXDUnitProvider(image=cfg.image)
        case "multipass":
            return MultipassUnitProvider(image=cfg.image)
        case "ssh":
            return SSHUnitProvider(hosts=cfg.hosts)
        case _:
            raise ValueError(f"Unknown provider type: {cfg.type!r}")
