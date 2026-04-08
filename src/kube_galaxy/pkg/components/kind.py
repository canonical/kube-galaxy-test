"""
Kind component installation and management.

Kind is used to bootstrap Kubernetes clusters.  The actual cluster
provisioning is performed by :class:`~kube_galaxy.pkg.units.kind.KindUnitProvider`
(``kind create cluster``).  This component's main responsibilities are:

* Exporting the kubeconfig via ``kind export kubeconfig`` and pushing it
  into the Kind control-plane container at the canonical
  ``/opt/kube-galaxy/tests/kubeconfig`` location so that all subsequent
  ``kubectl`` calls can find it.
* Acting as the cluster-manager marker so the orchestrator recognises
  exactly one :class:`ClusterComponentBase` in the manifest.
"""

from kube_galaxy.pkg.components import ClusterComponentBase, register_component
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import NodeRole
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.kubeconfig import host_ip
from kube_galaxy.pkg.utils.logging import info, success
from kube_galaxy.pkg.utils.paths import ensure_dir
from kube_galaxy.pkg.utils.shell import run


@register_component("kind")
class Kind(ClusterComponentBase):
    """
    Kind component for bootstrapping Kubernetes clusters.

    This component handles bootstrapping Kubernetes control
    planes using kind.
    """

    # ------------------------------------------------------------------
    # ClusterComponentBase interface
    # ------------------------------------------------------------------

    def init_cluster(self) -> None:
        """No-op — the KindUnitProvider already created the cluster."""

    def generate_join_token(self, role: NodeRole) -> str:
        """No-op — kind handles node joining internally."""
        return ""

    def join_cluster(self, token: str, role: NodeRole) -> None:
        """No-op — kind handles node joining internally."""

    def pull_kubeconfig(self) -> None:
        """Export the kubeconfig using ``kind export kubeconfig``.

        Runs ``kind export kubeconfig --name <cluster> --kubeconfig <path>``
        on the orchestrator to write a properly configured kubeconfig (with
        the correct API server address) to the local staging directory, then
        pushes it into the container at the canonical
        :data:`SystemPaths.kube_config` path so that ``kubectl``
        (via ``client.py``) can locate it.
        """
        orchestrator_kube_config = SystemPaths.local_kube_config()
        ensure_dir(orchestrator_kube_config.parent)

        cluster_name = self.manifest.name
        result = run(
            [
                "kind",
                "export",
                "kubeconfig",
                f"--name={cluster_name}",
                f"--kubeconfig={orchestrator_kube_config}",
            ],
            check=False,
        )
        if result.returncode != 0:
            raise ComponentError(
                f"Failed to export kubeconfig for kind cluster '{cluster_name}': "
                f"{result.stderr}"
            )

        # The exported kubeconfig contains 0.0.0.0 as the server address
        # (from the kind networking config).  Replace it with the real host
        # IP so that kubectl can reach the API server from any context.
        host_ip_addr = host_ip()
        kubeconfig_text = orchestrator_kube_config.read_text()
        kubeconfig_text = kubeconfig_text.replace("0.0.0.0", host_ip_addr)
        orchestrator_kube_config.write_text(kubeconfig_text)
        info(f"Replaced 0.0.0.0 with host IP {host_ip_addr} in kubeconfig")

        # Copy the existing admin.conf inside the container to the canonical
        # kube-galaxy kubeconfig path so that kubectl calls via client.py
        # (which set KUBECONFIG to this path) work correctly.
        remote_kube_config = str(SystemPaths.kube_config())
        self.unit.run(["mkdir", "-p", str(SystemPaths.kube_config().parent)], check=True)
        self.unit.run(["cp", "/etc/kubernetes/admin.conf", remote_kube_config], check=True)
        success(f"Kubeconfig exported to {remote_kube_config}")
    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def bootstrap_hook(self) -> None:
        """Pull kubeconfig on the lead control-plane after kind creates the cluster.

        The Kind provider already bootstrapped the cluster, so there is no
        ``kubeadm init`` to run.  We only need to ensure the kubeconfig is
        available for subsequent ``kubectl`` calls.
        """
        # Run strategy hooks first (container-image is a no-op for bootstrap)
        super().bootstrap_hook()

        if (self.unit.role, self.unit.index) == (NodeRole.CONTROL_PLANE, 0):
            info("Pulling kubeconfig from Kind control-plane...")
            self.pull_kubeconfig()
