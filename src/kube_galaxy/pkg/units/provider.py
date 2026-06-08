"""UnitProvider ABC and concrete implementations for machine lifecycle management."""

import kube_galaxy.pkg.units.juju as juju
import kube_galaxy.pkg.units.lxdvm as lxdvm
import kube_galaxy.pkg.units.multipass as multipass
import kube_galaxy.pkg.units.ssh as ssh
from kube_galaxy.pkg.manifest.models import Manifest, NodesConfig, ProviderConfig
from kube_galaxy.pkg.units._base import UnitProvider
from kube_galaxy.pkg.units.local import LocalUnitProvider
from kube_galaxy.pkg.utils.artifact_server import ArtifactServer


def provider_factory(manifest: Manifest) -> UnitProvider:
    """Create the appropriate ``UnitProvider`` from a manifest's ``provider`` block.

    Defaults to ``LXDUnitProvider`` when no ``provider`` block is present
    (``provider.type`` defaults to ``"lxd"``).
    """
    cfg: ProviderConfig = manifest.provider
    node_cfg: NodesConfig = manifest.provider.nodes
    match cfg.type:
        case "local":
            return LocalUnitProvider(node_cfg, image=cfg.image)
        case "lxd":
            lxdvm.print_dependency_status()
            return lxdvm.LXDUnitProvider(node_cfg, image=cfg.image)
        case "multipass":
            multipass.print_dependency_status()
            return multipass.MultipassUnitProvider(node_cfg, image=cfg.image)
        case "ssh":
            ssh.print_dependency_status()
            return ssh.SSHUnitProvider(node_cfg, image="", hosts=cfg.hosts)
        case "juju":
            juju.print_dependency_status()
            tunnel_ports: list[int] = [ArtifactServer.DEFAULT_PORT]
            if manifest.artifact.registry.enabled:
                tunnel_ports.append(manifest.artifact.registry.port)
            return juju.JujuUnitProvider(node_cfg, image=cfg.image, tunnel_ports=tunnel_ports)
        case _:
            raise ValueError(f"Unknown provider type: {cfg.type!r}")
