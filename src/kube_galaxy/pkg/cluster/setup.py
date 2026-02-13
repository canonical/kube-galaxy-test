"""Cluster setup and provisioning using kubeadm."""

from pathlib import Path

from kube_galaxy.pkg.arch.detector import ArchInfo, get_arch_info
from kube_galaxy.pkg.components import configure_component, install_component
from kube_galaxy.pkg.manifest.loader import load_manifest
from kube_galaxy.pkg.manifest.models import Manifest
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.logging import error, info, section, success
from kube_galaxy.pkg.utils.shell import ShellError, run


def setup_cluster(manifest_path: str, work_dir: str = ".", debug: bool = False) -> None:
    """
    Set up a Kubernetes cluster using kubeadm.

    Args:
        manifest_path: Path to cluster manifest YAML
        work_dir: Working directory for artifacts
        debug: Enable debug output

    Raises:
        ClusterError: If cluster setup fails
    """
    try:
        # Load and validate manifest
        manifest = load_manifest(manifest_path)
        work_dir_path = Path(work_dir)

        section("Kubernetes Cluster Setup")
        info(f"Manifest: {manifest_path}")
        info(f"Work Dir: {work_dir}")
        info(f"Debug: {debug}")

        # Display configuration
        section("Configuration")
        info(f"Cluster Name: {manifest.name}")
        info(f"Kubernetes Version: {manifest.kubernetes_version}")
        info(f"Control Plane Nodes: {manifest.nodes.control_plane}")
        info(f"Worker Nodes: {manifest.nodes.worker}")

        # Detect architecture
        arch_info = get_arch_info()
        info(f"System Architecture: {arch_info.system}")
        info(f"Kubernetes Architecture: {arch_info.k8s}")
        info(f"Image Architecture: {arch_info.image}")

        # Create working directories
        work_dir_path.mkdir(parents=True, exist_ok=True)
        (work_dir_path / "components").mkdir(exist_ok=True)
        (work_dir_path / "logs").mkdir(exist_ok=True)

        # Install components
        _install_components(manifest, work_dir_path, arch_info, debug)

        # Initialize cluster with kubeadm
        _initialize_cluster(manifest, debug)

        # Verify cluster health
        _verify_cluster_health()

        section("Cluster Setup Complete!")
        success("Kubeconfig: $HOME/.kube/config")
        success(f"Cluster Name: {manifest.name}")
        success(f"Kubernetes Version: {manifest.kubernetes_version}")

    except Exception as exc:
        raise ClusterError(f"Cluster setup failed: {exc}") from exc


def _install_components(
    manifest: Manifest, work_dir: Path, arch_info: ArchInfo, debug: bool
) -> None:
    """Install all components from manifest."""
    section("Installing components")

    for i, component in enumerate(manifest.components, 1):
        info(f"Component [{i}/{len(manifest.components)}]: {component.name}")
        info(f"  Release: {component.release}")
        info(f"  Format: {component.format}")
        info(f"  Repo: {component.repo}")

        log_file = work_dir / "logs" / f"{component.name}.log"

        try:
            # Install component using dynamic component module
            install_component(
                component_name=component.name,
                repo=component.repo,
                release=component.release,
                format=component.format,
                arch=arch_info.k8s,
            )
            info("  ✓ Installed")

            # Configure component after installation
            configure_component(component.name)
            info("  ✓ Configured")

        except Exception as exc:
            error(f"  ✗ Installation failed: {exc}")
            if log_file.exists():
                error(f"  See {log_file} for details")
            raise


def _initialize_cluster(manifest: Manifest, debug: bool) -> None:
    """Initialize Kubernetes cluster with kubeadm."""
    section("Initializing cluster with kubeadm")

    # Get networking configuration
    networking = manifest.get_networking()
    if not networking:
        raise ClusterError("No networking configuration found in manifest")

    info("Networking Configuration:")
    info(f"  Service CIDR: {networking.service_cidr}")
    info(f"  Pod CIDR: {networking.pod_cidr}")

    # Check kubeadm availability
    try:
        run(["which", "kubeadm"], check=True, capture_output=True)
    except ShellError as exc:
        raise ClusterError("kubeadm not found in PATH") from exc

    # Initialize cluster
    cmd = [
        "sudo",
        "kubeadm",
        "init",
        f"--pod-network-cidr={networking.pod_cidr}",
        f"--service-cidr={networking.service_cidr}",
    ]

    if debug:
        info(f"Running: {' '.join(cmd)}")

    try:
        run(cmd, check=True)
        success("Cluster initialized with kubeadm")
    except ShellError as exc:
        raise ClusterError(f"kubeadm init failed: {exc}") from exc

    # Setup kubeconfig
    try:
        home = Path.home()
        kube_dir = home / ".kube"
        kube_dir.mkdir(exist_ok=True)

        run(["sudo", "cp", "/etc/kubernetes/admin.conf", str(kube_dir / "config")], check=True)
        owner = Path.home().owner()
        group = Path.home().group()
        run(["sudo", "chown", f"{owner}:{group}", str(kube_dir / "config")], check=True)
        success("Kubeconfig configured")
    except ShellError as exc:
        raise ClusterError(f"Failed to setup kubeconfig: {exc}") from exc


def _verify_cluster_health() -> None:
    """Verify cluster is healthy and ready."""
    section("Verifying cluster health")

    try:
        # Check cluster info
        info("Checking cluster connectivity...")
        run(["kubectl", "cluster-info"], check=True)

        # Wait for nodes
        info("Waiting for nodes to be ready...")
        run(
            ["kubectl", "wait", "--for=condition=Ready", "nodes", "--all", "--timeout=300s"],
            check=True,
        )

        # Wait for system pods
        info("Waiting for system pods to be ready...")
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

        # Display cluster info
        info("Cluster Information:")
        run(["kubectl", "get", "nodes", "-o", "wide"], check=True)
        run(["kubectl", "get", "pods", "-n", "kube-system"], check=True)

        success("Cluster is healthy and ready")

    except ShellError as exc:
        raise ClusterError(f"Cluster verification failed: {exc}") from exc
