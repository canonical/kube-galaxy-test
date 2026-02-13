"""
Containerd component installation and management.

Containerd is the container runtime used by Kubernetes clusters.
"""

from pathlib import Path

from kube_galaxy.pkg.components import ComponentHooks, register_component_hooks
from kube_galaxy.pkg.utils.components import (
    download_file,
    extract_archive,
    install_binary,
    remove_binary,
)
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.shell import run

# Component timeout configuration (in seconds)
DOWNLOAD_TIMEOUT = 300  # 5 minutes (containerd archive can be large)
INSTALL_TIMEOUT = 120   # 2 minutes (extract and copy)
BOOTSTRAP_TIMEOUT = 60  # 1 minute (start service)
CONFIGURE_TIMEOUT = 60  # 1 minute (verify service running)

# Component-level variables for hook state
_download_state = {}


def download_hook(repo: str, release: str, format: str, arch: str) -> None:
    """
    Download containerd binary archive.
    
    This hook runs in the DOWNLOAD stage (can be parallelized).
    
    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v2.0.6')
        format: Installation format (Binary, Binary+Container)
        arch: Architecture (amd64, arm64, etc.)
    """
    # Ensure version has 'v' prefix
    if not release.startswith("v"):
        release = f"v{release}"
    
    # Construct download URL
    filename = f"containerd-{release}.linux-{arch}.tar.gz"
    url = f"{repo}/releases/download/{release}/{filename}"
    
    # Download to temporary directory
    temp_dir = Path("/tmp/containerd-install")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    archive_path = temp_dir / filename
    download_file(url, archive_path)
    
    # Extract archive
    extract_dir = temp_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)
    extract_archive(archive_path, extract_dir)
    
    # Store paths for install hook
    _download_state['extract_dir'] = extract_dir


def install_hook(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install containerd binary.
    
    This hook runs in the INSTALL stage.
    Requires download_hook to have completed first.
    
    Args:
        repo: GitHub repository URL (unused, from download)
        release: Release tag (unused, from download)
        format: Installation format (unused)
        arch: Architecture (unused, from download)
    """
    extract_dir = _download_state.get('extract_dir')
    if not extract_dir or not extract_dir.exists():
        raise ComponentError("containerd archive not downloaded. Run download hook first.")
    
    # Install binary
    binary_path = extract_dir / "bin" / "containerd"
    if not binary_path.exists():
        raise ComponentError(f"containerd binary not found in archive at {binary_path}")
    
    install_binary(binary_path, "containerd")


def configure_hook() -> None:
    """
    Configure containerd.
    
    This hook runs in the CONFIGURE stage.
    Creates systemd service unit and default configuration.
    """
    # Create systemd service unit
    systemd_unit = """[Unit]
Description=containerd container runtime
Documentation=https://containerd.io
After=network.target local-fs.target

[Service]
ExecStart=/usr/local/bin/containerd
ExecStop=/bin/kill -s TERM $MAINPID
Restart=on-failure
RestartSec=5
Delegate=yes
KillMode=process
OOMScoreAdjust=-999
LimitNOFILE=1048576
LimitNPROC=infinity

[Install]
WantedBy=multi-user.target
"""
    
    unit_path = Path("/etc/systemd/system/containerd.service")
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(systemd_unit)
    
    # Reload systemd and enable service
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "containerd"])


def bootstrap_hook() -> None:
    """
    Bootstrap containerd.
    
    This hook runs in the BOOTSTRAP stage.
    Starts the containerd service.
    """
    run(["systemctl", "start", "containerd"])


# Legacy compatibility functions (maintain existing API)
def install(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install containerd binary (legacy API).
    
    For backward compatibility. New code should use hooks.
    
    Args:
        repo: GitHub repository URL
        release: Release tag (e.g., 'v2.0.6')
        format: Installation format (Binary, Binary+Container)
        arch: Architecture (amd64, arm64, etc.)
    """
    download_hook(repo, release, format, arch)
    install_hook(repo, release, format, arch)


def configure() -> None:
    """
    Configure containerd (legacy API).
    
    For backward compatibility. New code should use hooks.
    """
    configure_hook()
    bootstrap_hook()


def remove() -> None:
    """
    Remove containerd.

    Stops service and removes binary.
    """
    try:
        run(["systemctl", "stop", "containerd"], check=False)
        run(["systemctl", "disable", "containerd"], check=False)
    except Exception:
        pass

    remove_binary("containerd")

    # Remove systemd unit
    unit_path = Path("/etc/systemd/system/containerd.service")
    if unit_path.exists():
        unit_path.unlink()

    run(["systemctl", "daemon-reload"], check=False)


# Register component hooks
_containerd_hooks = ComponentHooks(
    name="containerd",
    category="containerd",
    download=download_hook,
    pre_install=None,  # No pre-install needed
    install=install_hook,
    bootstrap=bootstrap_hook,
    post_bootstrap=None,  # No post-bootstrap needed
    configure=configure_hook,
    dependencies=["runc"],  # Needs runc first
    priority=10,  # Install very early (container runtime needed by others)
    # Custom timeouts for this component
    download_timeout=DOWNLOAD_TIMEOUT,
    install_timeout=INSTALL_TIMEOUT,
    bootstrap_timeout=BOOTSTRAP_TIMEOUT,
    configure_timeout=CONFIGURE_TIMEOUT,
)

register_component_hooks(_containerd_hooks)
