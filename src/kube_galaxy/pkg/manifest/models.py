"""Manifest data models for kube-galaxy."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from kube_galaxy.pkg.literals import URLs


class NodeRole(StrEnum):
    """Role of a node in the cluster."""

    CONTROL_PLANE = "control-plane"
    WORKER = "worker"


class Placement(StrEnum):
    """Which nodes a component is placed on."""

    ALL = "all"
    CONTROL_PLANE = "control-plane"
    WORKERS = "workers"
    ORCHESTRATOR = "orchestrator"


class InstallMethod(StrEnum):
    """Installation method for components."""

    BINARY = "binary"  # Direct binary download and install
    BINARY_ARCHIVE = "binary-archive"  # Binary in tar/zip/xz archive from releases
    CONTAINER_IMAGE = "container-image"  # Container image from registry
    CONTAINER_IMAGE_ARCHIVE = "container-image-archive"  # Container image in tar archive
    CONTAINER_MANIFEST = "container-manifest"  # Kubernetes YAML manifest file
    HELM = "helm" # Helm char from a chart repository
    NONE = "none"  # No installation, component has no installable artifacts


class TestMethod(StrEnum):
    """Test execution method for components."""

    NONE = "none"  # No tests for this component
    SPREAD = "spread"  # Spread test suite


@dataclass
class RepoInfo:
    """Repository information for component source code.

    Supports multiple source modes via URL schemes in ``base_url``:

    - Remote:      ``https://github.com/org/repo``
    - Local:       ``local://path/relative/to/cwd``  — expands to a ``file://`` URI
    - GH Artifact: ``gh-artifact://artifact-name/path/in/zip``
    """

    base_url: str = ""  # Repository URL (scheme-based: https://, local://, gh-artifact://)
    subdir: str | None = None  # Optional subdirectory within repo for monorepos
    ref: str | None = None  # Optional git reference (branch/tag/commit), defaults to release


@dataclass
class InstallConfig:
    """Kubernetes component installation configuration."""

    method: InstallMethod  # Installation method
    source_format: str  # e.g., format string URL or path to binary, chart, or manifest
    retag_format: str  # e.g. format string for retagging container images to pull through registry
    bin_path: str  # Default path inside archive where binaries
    repo: RepoInfo = field(default_factory=RepoInfo)  # Repository for this install artefact


@dataclass
class TestConfig:
    """Spread test configuration for a component.

    Describes how to locate and run the component's spread test suite.
    The ``repo`` field identifies where to find the test tasks (local or
    remote), and ``source_format`` is a Mustache template that resolves to
    the root directory of the test suite (e.g.
    ``{{ repo.base-url }}/components/{{ name }}``).
    """

    method: TestMethod  # Test execution method
    source_format: str  # Mustache template resolving to the test suite root
    repo: RepoInfo = field(default_factory=RepoInfo)  # Repository hosting the test suite
    # Environment variables for test execution
    environment: dict[str, str] = field(default_factory=dict)


@dataclass
class NodesConfig:
    """Node count configuration.

    Defaults to ``control-plane: 1, worker: 0`` when the ``nodes`` block is
    absent from a manifest, preserving backward-compatible single-node behaviour.
    """

    control_plane: int = 1
    worker: int = 0


@dataclass
class ProviderConfig:
    """Provider configuration for cluster nodes.

    Defaults to ``type: lxd`` when the ``provider`` block is absent from a
    manifest.
    """

    type: str = "lxd"  # local | lxd | multipass | ssh
    image: str = "ubuntu:24.04"  # base image for lxd / multipass providers
    nodes: NodesConfig = field(
        default_factory=NodesConfig
    )  # node counts for each role (lxd/multipass)
    hosts: list[str] = field(default_factory=list)  # pre-existing hosts for ssh provider


@dataclass
class ComponentConfig:
    """Kubernetes component configuration from manifest YAML."""

    name: str
    category: str
    release: str
    installation: InstallConfig
    test: TestConfig = field(
        default_factory=lambda: TestConfig(method=TestMethod.NONE, source_format="")
    )  # Defaults to no-test config; set method=spread to enable spread tests

    # Component lifecycle configuration
    dependencies: list[str] = field(default_factory=list)  # Must install after these components
    placement: Placement = Placement.ALL  # Which nodes this component is placed on


@dataclass
class NetworkConfig:
    """Network configuration for cluster."""

    name: str
    service_cidr: str
    pod_cidr: str


@dataclass
class RegistryConfig:
    """Pull-through container registry configuration.

    When ``enabled`` is ``True``, a Docker-based registry cache is started on
    the orchestrator host and Kubernetes nodes are configured to pull
    ``remote_registry`` images through it.  The registry data directory is
    always ``SystemPaths.staging_root() / "registry" / "data"`` — it is not
    user-configurable.
    """

    enabled: bool = True
    remote_registry: str = URLs.REGISTRY_K8S_IO
    port: int = 5000


@dataclass
class ArtifactConfig:
    """Artifact-server configuration for the orchestrator.

    Groups settings for orchestrator-hosted servers that distribute artifacts
    to cluster nodes (HTTP artifact server, pull-through registry cache, …).
    """

    registry: RegistryConfig = field(default_factory=RegistryConfig)


@dataclass
class Manifest:
    """Cluster manifest configuration."""

    name: str
    kubernetes_version: str
    path: Path = Path("")  # Path to manifest file (optional; used for logging/debugging)
    description: str = ""
    components: list[ComponentConfig] = field(default_factory=list)
    networking: list[NetworkConfig] = field(default_factory=list)
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    artifact: ArtifactConfig = field(default_factory=ArtifactConfig)

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
