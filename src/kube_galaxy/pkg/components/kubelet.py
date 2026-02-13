"""
Kubelet component installation and management.

Kubelet is the primary node agent running on each node.
"""

from pathlib import Path

from kube_galaxy.pkg.utils.components import (
    download_file,
    install_binary,
    remove_binary,
)
from kube_galaxy.pkg.utils.shell import run


def install(repo: str, release: str, format: str, arch: str) -> None:
    """
    Install kubelet binary.

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
    filename = "kubelet"
    url = f"{repo}/releases/download/{release}/bin/linux/{arch}/{filename}"

    # Download binary
    temp_dir = Path("/tmp/kubelet-install")
    temp_dir.mkdir(parents=True, exist_ok=True)

    binary_path = temp_dir / "kubelet"
    download_file(url, binary_path)

    # Install binary
    install_binary(binary_path, "kubelet")


def configure() -> None:
    """
    Configure kubelet.

    Creates systemd service unit for kubelet.
    """
    systemd_unit = """[Unit]
Description=kubelet: The Kubernetes Node Agent
Documentation=https://kubernetes.io/docs/
After=containerd.service

[Service]
ExecStart=/usr/local/bin/kubelet \\
  --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf \\
  --kubeconfig=/etc/kubernetes/kubelet.conf \\
  --config=/etc/kubernetes/kubelet-config.yaml \\
  --container-runtime-endpoint=unix:///var/run/containerd/containerd.sock
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

    unit_path = Path("/etc/systemd/system/kubelet.service")
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(systemd_unit)

    # Reload systemd
    run(["systemctl", "daemon-reload"], check=False)


def remove() -> None:
    """
    Remove kubelet.

    Stops service and removes binary.
    """
    try:
        run(["systemctl", "stop", "kubelet"], check=False)
        run(["systemctl", "disable", "kubelet"], check=False)
    except Exception:
        pass

    remove_binary("kubelet")

    # Remove systemd unit
    unit_path = Path("/etc/systemd/system/kubelet.service")
    if unit_path.exists():
        unit_path.unlink()

    run(["systemctl", "daemon-reload"], check=False)
