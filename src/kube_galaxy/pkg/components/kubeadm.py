"""
Kubeadm component installation and management.

Kubeadm is used to bootstrap Kubernetes clusters.
"""

import shlex
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import yaml

from kube_galaxy.pkg.components import ClusterComponentBase, register_component
from kube_galaxy.pkg.literals import SystemPaths, URLs
from kube_galaxy.pkg.manifest.models import NodeRole
from kube_galaxy.pkg.utils.client import (
    get_api_server_status,
    verify_connectivity,
    wait_for_nodes,
)
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.paths import ensure_dir


@register_component("kubeadm")
class Kubeadm(ClusterComponentBase):
    """
    Kubeadm component for bootstrapping Kubernetes clusters.

    This component handles downloading, installing, and bootstrapping
    Kubernetes control planes using kubeadm.
    """

    # Timeout configuration (in seconds)

    _cluster_config: Path | None = None

    def _system_settings(self) -> None:
        """
        Apply necessary system settings for kubeadm.
        """
        # Enable IP forwarding for kubeadm networking
        info("    Setting net.ipv4.ip_forward = 1")
        self.unit.run(["sysctl", "-w", "net.ipv4.ip_forward=1"], privileged=True)

    def _update_cluster_config(self, config: dict[str, Any]) -> None:
        """
        Update kubeadm ClusterConfiguration with necessary settings.

        This includes setting the Kubernetes version, control plane endpoint,
        and networking configuration based on the manifest.
        """

        # Get networking configuration from manifest
        networking = self.manifest.get_networking()
        if not networking:
            raise ComponentError("No networking configuration found in manifest")

        registry_address = ""
        if mirror := self._ctx.registry_mirror:
            registry_address = mirror.registry_address()

        config["networking"].update(
            {
                "podSubnet": networking.pod_cidr,
                "serviceSubnet": networking.service_cidr,
            }
        )
        config["clusterName"] = self.manifest.name
        config["kubernetesVersion"] = self.manifest.kubernetes_version
        if registry_address:
            config["imageRepository"] = registry_address
            config["dns"].update({"imageRepository": registry_address})
            config["etcd"].update({"imageRepository": registry_address})

    def _update_init_config(self, config: dict[str, Any]) -> None:
        """
        Update kubeadm InitConfiguration with necessary settings.

        This includes setting the API server advertise address and other
        control plane settings.
        """
        config["nodeRegistration"]["taints"] = []
        config["nodeRegistration"]["name"] = self.unit.hostname()
        config["localAPIEndpoint"]["advertiseAddress"] = "0.0.0.0"

    def configure_hook(self) -> None:
        """
        Configure system for kubeadm.

        Disables swap which is required for kubelet/kubeadm to work properly.
        """
        self._system_settings()

        # Configure kubeadm.service based on Kubernetes release repository
        info("  Installing kubelet configs")
        service_url = f"{URLs.K8S_RELEASE_BASE}/cmd/krel/templates/latest/kubeadm/10-kubeadm.conf"
        with urlopen(service_url) as response:
            service_content = response.read().decode("utf-8")

        # Write kubelet configuration for kubeadm (10-kubeadm.conf)
        service_content = service_content.replace(
            "/usr/bin/kubelet", f"{SystemPaths.USR_LOCAL_BIN}/kubelet"
        )

        # Use base method to write config file
        self.write_config_file(
            service_content, "/usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf"
        )

        if not self.manifest:
            raise ComponentError("Manifest required for kubeadm bootstrap")

        result = self.unit.run(["kubeadm", "config", "print", "init-defaults"], check=True)
        configs = list(yaml.safe_load_all(result.stdout))
        for config in configs:
            match config.get("kind"):
                case "InitConfiguration":
                    self._update_init_config(config)
                case "ClusterConfiguration":
                    self._update_cluster_config(config)
        self._cluster_config = self.component_dir / "temp/kubeadm-config.yaml"

        # Write config to temp file
        config_content = yaml.safe_dump_all(configs)
        self.write_config_file(config_content, self._cluster_config)

    # ------------------------------------------------------------------
    # ClusterComponentBase implementation
    # ------------------------------------------------------------------

    def init_cluster(self) -> None:
        """Bootstrap the initial control-plane on this unit."""
        if not self._cluster_config or not self.unit.path_exists(self._cluster_config):
            raise ComponentError("Cluster config not generated. Run configure hook first.")
        self.unit.run(
            ["kubeadm", "init", f"--config={self._cluster_config}"],
            privileged=True,
        )

    def pull_kubeconfig(self) -> None:
        """Pull kubeconfig from this unit to the orchestrator's /opt/kube-galaxy/.kube/config."""
        orchestrator_kube_config = SystemPaths.local_kube_config()
        ensure_dir(orchestrator_kube_config.parent)
        self.unit.get("/etc/kubernetes/admin.conf", orchestrator_kube_config)
        self.unit.put(orchestrator_kube_config, str(SystemPaths.kube_config()))

    def generate_join_token(self, role: NodeRole) -> str:
        """Generate a single-use join token on the control-plane unit."""
        result = self.unit.run(
            ["kubeadm", "token", "create", "--print-join-command"],
            privileged=True,
            check=True,
        )
        return result.stdout.strip()

    def join_cluster(self, token: str, role: NodeRole) -> None:
        """Join this unit to the cluster using the token from generate_join_token()."""
        # token is the full join command returned by kubeadm token create --print-join-command
        # shlex.split() safely parses the command string into a list for subprocess execution
        self.unit.run(shlex.split(token), privileged=True, check=True)

    def bootstrap_hook(self) -> None:
        """
        Bootstrap Kubernetes cluster with kubeadm init.

        This is where the cluster is actually created.
        """
        self.init_cluster()
        self.pull_kubeconfig()

    def verify_hook(self) -> None:
        """
        Verify cluster is healthy and ready.

        Checks cluster connectivity and waits for nodes/pods to be ready.
        """
        verify_connectivity(self.unit)
        wait_for_nodes(self.unit, timeout=300)
        get_api_server_status(self.unit, timeout=300)

    def stop_hook(self) -> None:
        """
        Stop the Kubernetes cluster using kubeadm reset.

        This performs a kubeadm reset to cleanly shut down the cluster,
        removing the node from the cluster and cleaning up cluster state.
        """
        info("Performing kubeadm reset to stop cluster")
        self.unit.run(["kubeadm", "reset", "--force"], privileged=True)
        info("Kubeadm reset completed successfully")

    def delete_hook(self) -> None:
        """
        Remove kubeadm binary and cluster configuration files.
        """
        super().delete_hook()  # This will handle alternatives and binaries

        # Use base method to remove kubeconfig files
        kubeconfig_paths = [
            Path("/etc/kubernetes/admin.conf"),
            self._cluster_config,
        ]
        self.remove_config_files([p for p in kubeconfig_paths if p and p.exists()])

    def post_delete_hook(self) -> None:
        """
        Clean up remaining Kubernetes cluster directories and files.
        """
        # Use base method to remove Kubernetes cluster directories
        k8s_dirs = [
            "/var/lib/etcd",
            "/etc/kubernetes",
            "/etc/cni/net.d",
        ]
        self.remove_directories(k8s_dirs, "Kubernetes")
