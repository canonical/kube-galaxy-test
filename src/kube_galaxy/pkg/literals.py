"""
Centralized literals and constants for the kube-galaxy project.

This module consolidates scattered string literals, magic numbers, and constants
to provide a single source of truth and improve maintainability.
"""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar


# Lifecycle stage enumeration
class SetupHooks(StrEnum):
    """Component lifecycle stages executed in order."""

    DOWNLOAD = "download"
    PRE_INSTALL = "pre_install"
    INSTALL = "install"
    CONFIGURE = "configure"
    BOOTSTRAP = "bootstrap"
    VERIFY = "verify"


# Teardown stage enumeration
class TeardownHooks(StrEnum):
    """Component teardown stages executed in order."""

    STOP = "stop"
    DELETE = "delete"
    POST_DELETE = "post_delete"


class SystemPaths:
    """System directory and file paths."""

    # Core kube-galaxy directories
    KUBE_GALAXY_ROOT = "/opt/kube-galaxy"
    KUBE_GALAXY_BIN_SUFFIX = "bin"
    KUBE_GALAXY_TEMP_SUFFIX = "temp"

    # System binaries
    USR_LOCAL_BIN = "/usr/local/bin"

    # Kubernetes directories
    ETC_KUBERNETES = "/etc/kubernetes"
    VAR_LIB_KUBELET = "/var/lib/kubelet"
    VAR_LIB_ETCD = "/var/lib/etcd"

    # Containerd directories
    ETC_CONTAINERD = "/etc/containerd"
    VAR_LIB_CONTAINERD = "/var/lib/containerd"

    @classmethod
    def component_dir(cls, component_name: str) -> Path:
        """Get component-specific directory path."""
        return Path(cls.KUBE_GALAXY_ROOT) / component_name

    @classmethod
    def component_bin_dir(cls, component_name: str) -> Path:
        """Get component bin directory path."""
        return cls.component_dir(component_name) / cls.KUBE_GALAXY_BIN_SUFFIX

    @classmethod
    def component_temp_dir(cls, component_name: str) -> Path:
        """Get component temp directory path."""
        return cls.component_dir(component_name) / cls.KUBE_GALAXY_TEMP_SUFFIX


class ConfigFiles:
    """Configuration file names and paths."""

    # Containerd
    CONTAINERD_CONFIG_TOML = "config.toml"
    CONTAINERD_SERVICE = "containerd.service"

    # Kubernetes
    KUBEADM_CONFIG_YAML = "kubeadm-config.yaml"
    ADMIN_CONF = "admin.conf"
    KUBELET_CONFIG_YAML = "config.yaml"
    KUBELET_SERVICE = "kubelet.service"


class Commands:
    """Common shell command patterns."""

    # sudo commands
    SUDO_MKDIR_P: ClassVar[list[str]] = ["sudo", "mkdir", "-p"]
    SUDO_CP: ClassVar[list[str]] = ["sudo", "cp"]
    SUDO_RM_RF: ClassVar[list[str]] = ["sudo", "rm", "-rf"]
    SUDO_TEE: ClassVar[list[str]] = ["sudo", "tee"]
    SUDO_CHMOD: ClassVar[list[str]] = ["sudo", "chmod"]
    SUDO_CHOWN: ClassVar[list[str]] = ["sudo", "chown"]
    SUDO_SYMLINK: ClassVar[list[str]] = ["sudo", "ln", "-s"]

    # apt commands
    SUDO_APT_REMOVE: ClassVar[list[str]] = ["sudo", "apt", "remove"]

    # ctr images
    SUDO_CTR_IMAGES: ClassVar[list[str]] = ["sudo", "ctr", "-n", "k8s.io", "images"]

    # systemctl commands
    SYSTEMCTL_DAEMON_RELOAD: ClassVar[list[str]] = ["sudo", "systemctl", "daemon-reload"]
    SYSTEMCTL_ENABLE: ClassVar[list[str]] = ["sudo", "systemctl", "enable"]
    SYSTEMCTL_DISABLE: ClassVar[list[str]] = ["sudo", "systemctl", "disable"]
    SYSTEMCTL_IS_ACTIVE: ClassVar[list[str]] = ["sudo", "systemctl", "is-active"]
    SYSTEMCTL_START: ClassVar[list[str]] = ["sudo", "systemctl", "start"]
    SYSTEMCTL_STOP: ClassVar[list[str]] = ["sudo", "systemctl", "stop"]
    SYSTEMCTL_RESTART: ClassVar[list[str]] = ["sudo", "systemctl", "restart"]

    # update-alternatives commands
    UPDATE_ALTERNATIVES_INSTALL: ClassVar[list[str]] = ["sudo", "update-alternatives", "--install"]
    UPDATE_ALTERNATIVES_REMOVE: ClassVar[list[str]] = ["sudo", "update-alternatives", "--remove"]
    UPDATE_ALTERNATIVES_REMOVE_ALL: ClassVar[list[str]] = [
        "sudo",
        "update-alternatives",
        "--remove-all",
    ]

    # kubectl commands
    K_CREATE_DRY_RUN: ClassVar[list[str]] = ["kubectl", "create", "--dry-run=client", "-o", "yaml"]
    K_ROLLOUT_STATUS: ClassVar[list[str]] = ["kubectl", "rollout", "status"]


class Permissions:
    """File permissions and system priorities."""

    # File permissions
    EXECUTABLE = "755"
    READABLE = "644"
    PRIVATE = "600"

    # update-alternatives priority
    ALTERNATIVES_PRIORITY = "100"


class URLs:
    """URL patterns and registry endpoints."""

    # GitHub
    GITHUB_BASE = "https://github.com"
    GITHUB_RELEASES_PATTERN = "https://github.com/{repo}/releases/download/{release}/{filename}"
    GITHUB_RAW_CONTENT = "https://raw.githubusercontent.com"

    # Kubernetes release URLs
    K8S_RELEASE_BASE = "https://raw.githubusercontent.com/kubernetes/release/v0.16.2"

    # Container registries
    REGISTRY_K8S_IO = "registry.k8s.io"


class TestDirectories:
    """Test and output directory names."""

    TEST_RESULTS = "test-results"
    SPREAD_RESULTS = "spread-results"
    DEBUG_LOGS = "debug-logs"
    CLEANUP_LOGS = "cleanup-logs"
    ISSUE_DATA = "issue-data"


class Timeouts:
    """Timeout values in seconds."""

    # Download and network operations
    NETWORK_TIMEOUT = 60  # 1 minute

    # Cluster operations
    BOOTSTRAP_TIMEOUT = 600  # 10 minutes
    JOIN_TIMEOUT = 180  # 3 minutes

    # Service operations
    SERVICE_START_TIMEOUT = 30  # 30 seconds
    SERVICE_STOP_TIMEOUT = 30  # 30 seconds


class FilePatterns:
    """File name patterns and extensions."""

    YAML_GLOB = "*.yaml"
    LOG_GLOB = "*.log"

    # Test files
    TEST_CLUSTER_CONFIG = "test-cluster-config.yaml"
    SPREAD_YAML = "spread.yaml"


class ContainerdConfig:
    """Containerd-specific configuration values."""

    # Configuration directives
    SYSTEMD_CGROUP_FALSE = "SystemdCgroup = false"
    SYSTEMD_CGROUP_TRUE = "SystemdCgroup = true"

    # Default sandbox image
    SANDBOX_IMAGE = 'sandbox_image = "registry.k8s.io/pause:3.8"'


class NetworkDefaults:
    """Default network configuration values."""

    SERVICE_CIDR = "10.96.0.0/12"
    POD_CIDR = "192.168.0.0/16"


class ManifestFields:
    """YAML manifest field names."""

    USE_SPREAD = "use-spread"
    KUBERNETES_VERSION = "kubernetes-version"
    NAME = "name"
    RELEASE = "release"
    REPO = "repo"
    FORMAT = "format"
    COMPONENTS = "components"
    NETWORKING = "networking"
