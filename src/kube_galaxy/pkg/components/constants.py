"""
Constants for component installation methods and configuration.

This module defines the supported installation methods for components
and provides timeout defaults for lifecycle stages.
"""

from enum import StrEnum


class InstallMethod(StrEnum):
    """
    Installation methods for components.

    Binary methods define how binaries are installed.
    Container methods define how containers/services are deployed.
    """

    # Binary installation methods
    BINARY_ARCHIVE = "binary-archive"  # Extract from tar.gz, tar.xz, etc.
    BINARY_DIRECT = "binary-direct"  # Direct binary download (no extraction)
    BINARY_DEB = "binary-deb"  # Debian package installation
    BINARY_SNAP = "binary-snap"  # Snap package installation
    BINARY_RPM = "binary-rpm"  # RPM package installation

    # Container/service deployment methods
    POD_MANIFEST = "pod-manifest"  # Kubernetes Pod manifest (YAML)
    DEPLOYMENT_MANIFEST = "deployment-manifest"  # Kubernetes Deployment manifest
    DAEMONSET_MANIFEST = "daemonset-manifest"  # Kubernetes DaemonSet manifest
    HELM_CHART = "helm-chart"  # Helm chart installation
    KUSTOMIZE = "kustomize"  # Kustomize deployment

    # Hybrid/special methods
    KUBEADM_COMPONENT = "kubeadm-component"  # Installed via kubeadm (e.g., kube-apiserver)
    SYSTEMD_SERVICE = "systemd-service"  # Systemd service (containerd, kubelet)


class ArchiveFormat(StrEnum):
    """Supported archive formats for binary extraction."""

    TAR_GZ = "tar.gz"
    TAR_XZ = "tar.xz"
    TAR_BZ2 = "tar.bz2"
    ZIP = "zip"
    GZIP = "gz"


# Default timeout values (in seconds) for lifecycle stages
DEFAULT_DOWNLOAD_TIMEOUT = 300  # 5 minutes
DEFAULT_PRE_INSTALL_TIMEOUT = 60  # 1 minute
DEFAULT_INSTALL_TIMEOUT = 120  # 2 minutes
DEFAULT_BOOTSTRAP_TIMEOUT = 300  # 5 minutes (kubeadm init can be slow)
DEFAULT_POST_BOOTSTRAP_TIMEOUT = 60  # 1 minute
DEFAULT_CONFIGURE_TIMEOUT = 60  # 1 minute

# Connection pool size for parallel downloads
DOWNLOAD_POOL_SIZE = 5  # Maximum concurrent downloads

# Error handling strategy
FAIL_FAST = True  # Fail immediately on first error (no retries)
