"""
Kubeadm component installation and management.

Kubeadm is used to bootstrap Kubernetes clusters.
"""

from pathlib import Path

from kube_galaxy.pkg.components import ComponentHooks, HookStage, register_component_hooks
from kube_galaxy.pkg.utils.components import (
    download_file,
    install_binary,
    remove_binary,
)

# Component timeout configuration (in seconds)
# These override the defaults from constants.py
DOWNLOAD_TIMEOUT = 180  # 3 minutes (kubeadm binary is small)
INSTALL_TIMEOUT = 60    # 1 minute (just copying binary)
BOOTSTRAP_TIMEOUT = 600  # 10 minutes (kubeadm init can be slow)
POST_BOOTSTRAP_TIMEOUT = 30  # 30 seconds (just copy kubeconfig)
CONFIGURE_TIMEOUT = 60  # 1 minute (verification)

# Component-level variables for hook state
_download_state = {}


def download_hook(repo: str, release: str, format: str, arch: str) -> None:
    """
    Download kubeadm binary.
    
    This hook runs in the DOWNLOAD stage (can be parallelized).
    
    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v1.33.4')
        format: Installation format (Binary)
        arch: Architecture (amd64, arm64, etc.)
    """
    # Ensure version has 'v' prefix
    if not release.startswith("v"):
        release = f"v{release}"
    
    # Construct download URL
    filename = "kubeadm"
    url = f"{repo}/releases/download/{release}/bin/linux/{arch}/{filename}"
    
    # Download to temporary directory
    temp_dir = Path("/tmp/kubeadm-install")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    binary_path = temp_dir / "kubeadm"
    download_file(url, binary_path)
    
    # Store download location for install hook
    _download_state['binary_path'] = binary_path


def install_hook(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install kubeadm binary.
    
    This hook runs in the INSTALL stage.
    Requires download_hook to have completed first.
    
    Args:
        repo: GitHub repository URL (unused, from download)
        release: Release tag (unused, from download)
        format: Installation format (unused)
        arch: Architecture (unused, from download)
    """
    binary_path = _download_state.get('binary_path')
    if not binary_path or not binary_path.exists():
        raise RuntimeError("kubeadm binary not downloaded. Run download hook first.")
    
    # Install binary to system
    install_binary(binary_path, "kubeadm")


def configure_hook() -> None:
    """
    Configure kubeadm.
    
    This hook runs in the CONFIGURE stage.
    Kubeadm configuration is typically handled during cluster bootstrap.
    """
    pass


def bootstrap_hook() -> None:
    """
    Bootstrap Kubernetes cluster with kubeadm.
    
    This hook runs in the BOOTSTRAP stage.
    Initializes the control plane using kubeadm init.
    """
    # This would contain kubeadm init logic
    # For now, it's a placeholder that should be implemented
    # in the cluster setup orchestration
    pass


def post_bootstrap_hook() -> None:
    """
    Post-bootstrap tasks for kubeadm.
    
    This hook runs in the POST_BOOTSTRAP stage.
    Gets kubeconfig and performs post-init configuration.
    """
    # This would:
    # 1. Copy /etc/kubernetes/admin.conf to ~/.kube/config
    # 2. Set proper permissions
    # 3. Export KUBECONFIG environment variable
    pass


# Legacy compatibility functions (maintain existing API)
def install(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install kubeadm binary (legacy API).
    
    For backward compatibility. New code should use hooks.
    
    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v1.33.4')
        format: Installation format (Binary)
        arch: Architecture (amd64, arm64, etc.)
    """
    download_hook(repo, release, format, arch)
    install_hook(repo, release, format, arch)


def configure() -> None:
    """
    Configure kubeadm (legacy API).
    
    For backward compatibility. New code should use hooks.
    """
    configure_hook()


def remove() -> None:
    """
    Remove kubeadm.

    Removes binary.
    """
    remove_binary("kubeadm")


# Register component hooks
_kubeadm_hooks = ComponentHooks(
    name="kubeadm",
    category="kubernetes/kubernetes",
    download=download_hook,
    pre_install=None,  # No pre-install needed
    install=install_hook,
    bootstrap=bootstrap_hook,
    post_bootstrap=post_bootstrap_hook,
    configure=configure_hook,
    dependencies=["containerd", "kubelet"],  # Needs container runtime and kubelet
    priority=30,  # Install relatively early
    # Custom timeouts for this component
    download_timeout=DOWNLOAD_TIMEOUT,
    install_timeout=INSTALL_TIMEOUT,
    bootstrap_timeout=BOOTSTRAP_TIMEOUT,
    post_bootstrap_timeout=POST_BOOTSTRAP_TIMEOUT,
    configure_timeout=CONFIGURE_TIMEOUT,
)

register_component_hooks(_kubeadm_hooks)
