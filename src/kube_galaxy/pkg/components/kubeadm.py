"""
Kubeadm component installation and management.

Kubeadm is used to bootstrap Kubernetes clusters.
"""

import shutil
from pathlib import Path
from typing import ClassVar
from urllib.request import urlopen

import yaml

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.literals import URLs
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.logging import info
from kube_galaxy.pkg.utils.shell import run


class Kubeadm(ComponentBase):
    """
    Kubeadm component for bootstrapping Kubernetes clusters.

    This component handles downloading, installing, and bootstrapping
    Kubernetes control planes using kubeadm.
    """

    # Component metadata
    CATEGORY = "kubernetes/kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = ["kubelet"]

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 180  # 3 minutes (kubeadm binary is small)
    INSTALL_TIMEOUT = 60  # 1 minute (just copying binary)
    BOOTSTRAP_TIMEOUT = 600  # 10 minutes (kubeadm init can be slow)
    POST_BOOTSTRAP_TIMEOUT = 30  # 30 seconds (just copy kubeconfig)
    VERIFY_TIMEOUT = 300  # 5 minutes (cluster health checks)
    CONFIGURE_TIMEOUT = 60  # 1 minute (configuration)

    _cluster_config: Path | None = None

    def configure_hook(self) -> None:
        """
        Configure system for kubeadm.

        Disables swap which is required for kubelet/kubeadm to work properly.
        """
        info("  Disabling swap...")
        run(["sudo", "swapoff", "-a"], check=True)

        # Download kubeadm.service from Kubernetes release repository
        info("  Installing kubelet configs")
        service_url = f"{URLs.K8S_RELEASE_BASE}/cmd/krel/templates/latest/kubeadm/10-kubeadm.conf"
        with urlopen(service_url) as response:
            service_content = response.read().decode("utf-8")

        # Write kubelet configuration for kubeadm (10-kubeadm.conf)
        kubelet = self._install_path("kubelet")
        service_content = service_content.replace("/usr/bin/kubelet", kubelet)

        # Use base method to write config file
        self.write_config_file(
            service_content, "/usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf"
        )

        if not self.manifest:
            raise ComponentError("Manifest required for kubeadm bootstrap")

        # Get networking configuration from manifest
        networking = self.manifest.get_networking()
        if not networking:
            raise ComponentError("No networking configuration found in manifest")

        cmd = ["kubeadm", "config", "print", "init-defaults"]
        config_str = run(cmd, check=True, capture_output=True)
        configs = list(yaml.safe_load_all(config_str.stdout))
        for config in configs:
            kind = config.get("kind")
            if kind == "InitConfiguration":
                config["localAPIEndpoint"]["advertiseAddress"] = "0.0.0.0"
            elif kind == "ClusterConfiguration":
                config["networking"].update(
                    {
                        "podSubnet": networking.pod_cidr,
                        "serviceSubnet": networking.service_cidr,
                    }
                )
                config["clusterName"] = self.manifest.name
        self._cluster_config = Path(self.component_tmp_dir) / "kubeadm-config.yaml"
        run(["sudo", "mkdir", "-p", str(self._cluster_config.parent)], check=True)

        # Write config to temp file via sudo
        config_content = yaml.safe_dump_all(configs)
        run(["sudo", "tee", str(self._cluster_config)], input=config_content, text=True, check=True)

    def bootstrap_hook(self) -> None:
        """
        Bootstrap Kubernetes cluster with kubeadm init.

        This is where the cluster is actually created.
        """

        if not self._cluster_config or not self._cluster_config.exists():
            raise ComponentError("Cluster config not generated. Run configure hook first.")

        # Initialize cluster
        cmd = ["sudo", "kubeadm", "init", f"--config={self._cluster_config}"]
        run(cmd, check=True)

    def post_bootstrap_hook(self) -> None:
        """
        Post-bootstrap tasks: setup kubeconfig for user.

        Copies kubeconfig to user directory and sets permissions.
        """
        home = Path.home()
        kube_dir = home / ".kube"
        kube_dir.mkdir(exist_ok=True)

        # Copy admin config
        run(
            ["sudo", "cp", "/etc/kubernetes/admin.conf", str(kube_dir / "config")],
            check=True,
        )

        # Set proper ownership
        owner = home.owner()
        group = home.group()
        run(["sudo", "chown", f"{owner}:{group}", str(kube_dir / "config")], check=True)

    def verify_hook(self) -> None:
        """
        Verify cluster is healthy and ready.

        Checks cluster connectivity and waits for nodes/pods to be ready.
        """

        # Check cluster info
        kubectl = self._install_path("kubectl")
        run([kubectl, "cluster-info"], check=True)

        # Wait for nodes to be ready
        run(
            [kubectl, "wait", "--for=condition=Ready", "nodes", "--all", "--timeout=300s"],
            check=True,
        )

        # Wait for system pods to be ready
        run(
            [
                kubectl,
                "wait",
                "--for=condition=Ready",
                "pods",
                "--all",
                "-n",
                "kube-system",
                "--timeout=300s",
            ],
            check=True,
        )

    def stop_hook(self) -> None:
        """
        Stop the Kubernetes cluster using kubeadm reset.

        This performs a kubeadm reset to cleanly shut down the cluster,
        removing the node from the cluster and cleaning up cluster state.
        """
        if not shutil.which("kubeadm"):
            info("kubeadm not found in PATH, skipping cluster reset")
            return

        info("Performing kubeadm reset to stop cluster")
        run(["sudo", "kubeadm", "reset", "--force"], check=True)
        info("Kubeadm reset completed successfully")

    def delete_hook(self) -> None:
        """
        Remove kubeadm binary and cluster configuration files.
        """
        # Use base method to remove installed binary
        self.remove_installed_binary()

        # Remove cluster configuration if it exists
        if self._cluster_config and self._cluster_config.exists():
            self._cluster_config.unlink()
            info(f"Removed cluster config: {self._cluster_config}")

        # Use base method to remove kubeconfig files
        kubeconfig_paths = [
            str(Path.home() / ".kube" / "config"),
            "/etc/kubernetes/admin.conf",
        ]
        self.remove_config_files(kubeconfig_paths)

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
