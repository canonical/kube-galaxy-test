"""UnitProvider ABC and concrete implementations for machine lifecycle management."""

import kube_galaxy.pkg.units.lxdvm as lxdvm
import kube_galaxy.pkg.units.multipass as multipass
import kube_galaxy.pkg.units.ssh as ssh
from kube_galaxy.pkg.manifest.models import Manifest, NodesConfig, ProviderConfig
from kube_galaxy.pkg.units._base import UnitProvider
from kube_galaxy.pkg.units.local import LocalUnitProvider


def provider_factory(manifest: Manifest) -> UnitProvider:
    """Create the appropriate ``UnitProvider`` from a manifest's ``provider`` block.

    Defaults to ``LXDUnitProvider`` when no ``provider`` block is present
    (``provider.type`` defaults to ``"lxd"``).
    """
    cfg: ProviderConfig = manifest.provider
    nodes: NodesConfig = manifest.provider.nodes
    match cfg.type:
        case "local":
            return LocalUnitProvider(nodes, image=cfg.image)
        case "lxd":
            lxdvm.print_dependency_status()
            return lxdvm.LXDUnitProvider(nodes, image=cfg.image)
        case "multipass":
            multipass.print_dependency_status()
            return multipass.MultipassUnitProvider(nodes, image=cfg.image)
        case "ssh":
            ssh.print_dependency_status()
            return ssh.SSHUnitProvider(nodes, image="", hosts=cfg.hosts)
        case _:
            raise ValueError(f"Unknown provider type: {cfg.type!r}")
