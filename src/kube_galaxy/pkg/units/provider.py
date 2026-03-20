"""UnitProvider ABC and concrete implementations for machine lifecycle management."""

from kube_galaxy.pkg.manifest.models import Manifest, ProviderConfig
from kube_galaxy.pkg.units._base import UnitProvider
from kube_galaxy.pkg.units.local import LocalUnitProvider
from kube_galaxy.pkg.units.lxdvm import LXDUnitProvider
from kube_galaxy.pkg.units.multipass import MultipassUnitProvider
from kube_galaxy.pkg.units.ssh import SSHUnitProvider


def provider_factory(manifest: Manifest) -> UnitProvider:
    """Create the appropriate ``UnitProvider`` from a manifest's ``provider`` block.

    Defaults to ``LXDUnitProvider`` when no ``provider`` block is present
    (``provider.type`` defaults to ``"lxd"``).
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
