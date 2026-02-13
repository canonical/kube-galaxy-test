"""
Kubeadm component installation and management.

Kubeadm is used to bootstrap Kubernetes clusters.
"""

from pathlib import Path
from typing import ClassVar
from urllib.request import urlopen

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.utils.components import (
    download_file,
    install_binary,
)
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
    COMPONENT_NAME = "kubeadm"
    CATEGORY = "kubernetes/kubernetes"
    DEPENDENCIES: ClassVar[list[str]] = ["containerd", "kubelet"]
    PRIORITY = 30

    # Timeout configuration (in seconds)
    DOWNLOAD_TIMEOUT = 180  # 3 minutes (kubeadm binary is small)
    INSTALL_TIMEOUT = 60  # 1 minute (just copying binary)
    BOOTSTRAP_TIMEOUT = 600  # 10 minutes (kubeadm init can be slow)
    POST_BOOTSTRAP_TIMEOUT = 30  # 30 seconds (just copy kubeconfig)
    VERIFY_TIMEOUT = 300  # 5 minutes (cluster health checks)
    CONFIGURE_TIMEOUT = 60  # 1 minute (configuration)

    def download_hook(self, arch: str) -> None:
        """
        Download kubeadm binary.

        Constructs download URL from self.config (repo, release, installation).
        """
        if not self.config:
            raise RuntimeError("Component config required for download")

        repo = self.config.repo
        release = self.config.release
        source_format = self.config.installation.source_format

        # Construct download URL from source_format template
        url = source_format.format(repo=repo, release=release, arch=arch)

        # Download to temporary directory
        temp_dir = Path("/tmp/kubeadm-install")
        temp_dir.mkdir(parents=True, exist_ok=True)

        binary_path = temp_dir / "kubeadm"
        download_file(url, binary_path)

        # Store download location as instance attribute
        self.binary_path = binary_path

    def install_hook(self, arch: str) -> None:
        """
        Install kubeadm binary to system.

        Requires download_hook to have completed first.
        """
        if not hasattr(self, "binary_path") or not self.binary_path.exists():
            raise RuntimeError("kubeadm binary not downloaded. Run download hook first.")

        # Install binary to system
        install_binary(self.binary_path, "kubeadm")

    def configure_hook(self) -> None:
        """
        Configure system for kubeadm.

        Disables swap which is required for kubelet/kubeadm to work properly.
        """
        info("  Disabling swap...")
        run(["sudo", "swapoff", "-a"], check=True)

        # Download kubeadm.service from Kubernetes release repository
        info("  Installing kubelet configs")
        service_url = "https://raw.githubusercontent.com/kubernetes/release/${RELEASE_VERSION}/cmd/krel/templates/latest/kubeadm/10-kubeadm.conf"
        with urlopen(service_url) as response:
            service_content = response.read().decode("utf-8")

        # Create systemd directories
        run(["sudo", "mkdir", "-p", "/usr/lib/systemd/system/kubelet.service.d"], check=True)

        # Write kubelet.service file
        temp_service = Path("/tmp/kubelet.service")
        temp_service.write_text(service_content)
        run(
            ["sudo", "tee", "/usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf"],
            input=service_content,
            text=True,
            check=True,
        )

    def bootstrap_hook(self) -> None:
        """
        Bootstrap Kubernetes cluster with kubeadm init.

        This is where the cluster is actually created.
        """
        if not self.manifest:
            raise ComponentError("Manifest required for kubeadm bootstrap")

        # Get networking configuration from manifest
        networking = self.manifest.get_networking()
        if not networking:
            raise ComponentError("No networking configuration found in manifest")

        # Initialize cluster
        cmd = [
            "sudo",
            "kubeadm",
            "init",
            f"--pod-network-cidr={networking.pod_cidr}",
            f"--service-cidr={networking.service_cidr}",
        ]

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
        run(["kubectl", "cluster-info"], check=True)

        # Wait for nodes to be ready
        run(
            ["kubectl", "wait", "--for=condition=Ready", "nodes", "--all", "--timeout=300s"],
            check=True,
        )

        # Wait for system pods to be ready
        run(
            [
                "kubectl",
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
