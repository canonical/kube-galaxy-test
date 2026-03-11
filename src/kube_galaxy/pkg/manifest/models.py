"""Manifest data models for kube-galaxy."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class InstallMethod(StrEnum):
    """Installation method for components."""

    BINARY = "binary"  # Direct binary download and install
    BINARY_ARCHIVE = "binary-archive"  # Binary in tar/zip/xz archive from releases
    CONTAINER_IMAGE = "container-image"  # Container image from registry
    CONTAINER_IMAGE_ARCHIVE = "container-image-archive"  # Container image in tar archive
    CONTAINER_MANIFEST = "container-manifest"  # Kubernetes YAML manifest file
    NONE = "none"  # No installation, component has no installable artifacts


@dataclass
class InstallConfig:
    """Kubernetes component installation configuration."""

    method: InstallMethod  # Installation method
    source_format: str  # e.g., format string URL or path to binary, chart, or manifest
    bin_path: str  # Default path inside archive where binaries


@dataclass
class RepoInfo:
    """Repository information for component source code.

    Supports two source modes:
    - Remote: set ``base_url`` to the repository URL
      (e.g. ``https://github.com/org/repo``)
    - Local:  set ``base_url`` to the string ``"local"``

    Use the ``is_local`` property to distinguish between the two modes.
    When local, the working directory is used as the root for resolving
    paths (e.g. ``{repo.base-url}`` expands to ``str(Path.cwd())``).
    """

    base_url: str = ""  # Repository URL, or the sentinel value "local"
    subdir: str | None = None  # Optional subdirectory within repo for monorepos
    ref: str | None = None  # Optional git reference (branch/tag/commit), defaults to release

    @property
    def is_local(self) -> bool:
        """Return True when this repository source is a local (cwd-based) path."""
        return self.base_url == "local"


@dataclass
class ComponentConfig:
    """Kubernetes component configuration from manifest YAML."""

    name: str
    category: str
    release: str
    repo: RepoInfo
    installation: InstallConfig
    test: bool = False

    # Component lifecycle configuration
    dependencies: list[str] = field(default_factory=list)  # Must install after these components


@dataclass
class NetworkConfig:
    """Network configuration for cluster."""

    name: str
    service_cidr: str
    pod_cidr: str


@dataclass
class Manifest:
    """Cluster manifest configuration."""

    name: str
    kubernetes_version: str
    path: Path = Path("")  # Path to manifest file (optional; used for logging/debugging)
    description: str = ""
    components: list[ComponentConfig] = field(default_factory=list)
    networking: list[NetworkConfig] = field(default_factory=list)

    def get_component(self, name: str) -> ComponentConfig | None:
        """Get component config by name."""
        for component in self.components:
            if component.name == name:
                return component
        return None

    def get_networking(self, name: str = "default") -> NetworkConfig | None:
        """Get network config by name."""
        for net in self.networking:
            if net.name == name:
                return net
        return self.networking[0] if self.networking else None
