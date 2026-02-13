# Kubernetes Galaxy Test

A scalable, multi-architecture testing infrastructure for Kubernetes using functional test suites that run on GitHub Actions. This project tests custom-built Kubernetes components using the canonical [spread](https://github.com/canonical/spread) testing framework, with architecture detection and per-component test orchestration.

## 🏗️ Architecture

- **Python CLI**: Modern `kube-galaxy` command-line tool (Python 3.12+)
- **Cluster Manifests**: Simple YAML configuration files defining Kubernetes cluster setups with component lists
- **Per-Component Definition**: Each component specifies its repo, release, and whether it provides tests
- **GitHub Actions**: Automatic provisioning, testing, and cleanup workflows
- **Multiarch Support**: Runtime architecture detection (amd64, arm64, riscv64, etc.)
- **Component-Driven Tests**: Tests live in component repos, referenced via `use-spread` flag
- **Kubeadm-Based Provisioning**: Real cluster setup without container-based shortcuts

## 🏃 Quick Start

### Prerequisites

- Python 3.12+ with `uv` or `pip`
- Git

### Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/canonical/kube-galaxy-test.git
   cd kube-galaxy-test
   ```

2. **Create Python environment** (using `uv`):
   ```bash
   uv venv
   source .venv/bin/activate
   ```

   Or with `venv`:
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install kube-galaxy with dev dependencies**:
   ```bash
   uv tool install -e .
   ```

### Basic Usage

1. **Validate the project**:
   ```bash
   kube-galaxy validate all
   ```

2. **Review a cluster manifest**:
   ```bash
   kube-galaxy test-manifest manifests/baseline-k8s-1.35.yaml
   ```

3. **Check project status**:
   ```bash
   kube-galaxy status
   ```

4. **Run tests**:
   ```bash
   # Run local validation tests
   kube-galaxy test local
   # Run spread tests against active cluster
   kube-galaxy test spread
   ```

## 📦 Available Manifests

The `manifests/` directory contains several pre-configured cluster definitions:

### Baseline Clusters (Run on `workflow_dispatch`)
- `baseline-k8s-1.33.yaml` - Full K8s 1.33.0 cluster with Calico CNI
- `baseline-k8s-1.34.yaml` - Full K8s 1.34.0 cluster with Calico CNI
- `baseline-k8s-1.35.yaml` - Full K8s 1.35.0 cluster with Calico CNI
- `baseline-k8s-1.36.yaml` - Full K8s 1.36.0 cluster with Calico CNI

These comprehensive manifests include full networking and are marked with `ci-skip-on-pr: "true"` to run only on manual workflow dispatch.

### Minimal Clusters (Run on PRs)
- `single-node-no-cni.yaml` - **Single-node cluster without CNI** (core components only)
  - **Runs automatically on all PRs** for fast validation
  - Perfect for testing core Kubernetes components in isolation
  - Single control-plane node (no workers)
  - No CNI plugin (nodes will be NotReady, control plane components validated)
  - Useful for CNI development, debugging, or learning
  - See [single-node-no-cni.md](manifests/single-node-no-cni.md) for detailed documentation

### CI Strategy
- **Pull Requests**: Fast validation with `single-node-no-cni.yaml` only (~5-10 minutes)
- **Workflow Dispatch**: Comprehensive testing with all manifests (~45-90 minutes per manifest)
- **Push to main**: Disabled (empty branches list) to avoid redundant runs after PR merge

**Example**: Testing the minimal cluster
```bash
# Inspect the manifest
kube-galaxy test-manifest manifests/single-node-no-cni.yaml

# Setup the cluster (nodes will be NotReady without CNI)
kube-galaxy test setup --manifest manifests/single-node-no-cni.yaml

# Verify control plane is running
kubectl get pods -n kube-system
kubectl get nodes  # Will show NotReady status

# Clean up
kube-galaxy cleanup all
```

## 📋 Manifest Structure

Cluster manifests define Kubernetes clusters in simple YAML format:

```yaml
name: baseline-cluster
description: "Standard 3-node cluster"
nodes:
  control-plane: 1
  worker: 2
kubernetes-version: "v1.29.0"
components:
  - name: containerd
    release: "v1.7.0"
    repo: "https://github.com/containerd/containerd"
    use-spread: false
  - name: kubeadm
    release: "v1.29.0"
    repo: "https://github.com/kubernetes/kubernetes"
    use-spread: false
  - name: my-custom-cni
    release: "main"
    repo: "https://github.com/myorg/custom-cni"
    use-spread: true
testing:
  suite: "functional-basic"
  timeout: "30m"
  parallel: true
infrastructure:
  provider: "github-actions"
  runner-size: "ubuntu-latest-4-cores"
networking:
  - name: "calico"
    service-cidr: "10.96.0.0/12"
    pod-cidr: "192.168.0.0/16"
storage:
  - name: "rawfile-localpv"
    provisioner: "https://github.com/openebs/rawfile-localpv"
security:
  rbac: true
  network-policies: true
  pod-security-standards: "restricted"
```

### Manifest Fields

- **name**: Unique cluster identifier
- **nodes**: Control plane and worker node counts
- **kubernetes-version**: Kubernetes version (informational)
- **components**: List of components to install
  - **name**: Component identifier
  - **release**: Git tag/branch to checkout
  - **repo**: Git repository URL
  - **use-spread**: If true, component provides spread tests (see below)
- **testing**: Test configuration
- **infrastructure**: GitHub Actions runner configuration
- **networking**: CNI and network settings
- **storage**: Storage provisioner configuration
- **security**: Security settings

## 🔧 Component Repositories

Each component repository must contain a `spread.yaml` file that defines:

1. **Install instructions** (required if component is used)
2. **Test definitions** (required if `use-spread: true`)

### Example Component spread.yaml

```yaml
project: my-component

prepare: |
  # Setup commands before tests
  sudo mkdir -p /etc/mycomponent

install: |
  #!/bin/bash
  set -e

  # Install from sources
  cd /tmp/my-component
  ./build.sh
  sudo ./install.sh

  # Verify installation
  mycomponent --version

execute: |
  # Component tests run here
  # Tests can reference component functionality

restore: |
  # Cleanup after tests
  sudo rm -rf /tmp/my-component
```

### Architecture Support

Component install scripts receive these environment variables:
- `ARCH`: System architecture from `uname -m` (x86_64, aarch64, riscv64, etc.)
- `K_ARCH`: Kubernetes architecture name (amd64, arm64, riscv64, etc.)
- `COMPONENT_RELEASE`: The release version being installed
- `COMPONENT_REPO`: The repository URL

## 🚀 GitHub Actions Workflow

The project uses two main custom actions:

### 1. setup-cluster

Provisions a Kubernetes cluster with custom components:

1. Detects system architecture
2. Installs base dependencies (yq, git, curl)
3. Parses cluster manifest
4. Clones each component from its repository
5. Executes component install scripts from spread.yaml
6. Initializes Kubernetes cluster with kubeadm
7. Configures networking (CNI)
8. Verifies cluster health

**Responsibility**: Infrastructure provisioning

### 2. run-spread-tests

Executes test suites defined in components and locally:

1. Installs spread testing framework
2. Scans manifest for components with `use-spread: true`
3. Clones component repositories
4. Executes spread tests from component spread.yaml files
5. Runs local tests if tests/ directory exists
6. Collects test artifacts and results

**Responsibility**: Test execution and results collection

### Separation of Concerns

- **setup-cluster**: "How do we build the cluster?"
- **run-spread-tests**: "How do we test it?"

Tests come from two sources:
1. **Component-provided tests**: Each component with `use-spread: true` provides its own tests
2. **Local tests**: `tests/` directory can contain infrastructure-level tests

## 🏛️ Multiarch Architecture Support

The infrastructure supports multiple architectures from the start:

1. **Runtime Detection**: `uname -m` detects the runner architecture
2. **Architecture Mapping**: Linux arch names map to Kubernetes names:
   - x86_64 → amd64
   - aarch64 → arm64
   - riscv64 → riscv64
   - ppc64le → ppc64le
   - s390x → s390x

3. **Dynamic Tool Installation**: Tools like yq and spread download for the detected architecture
4. **Component Awareness**: Install scripts receive both architecture formats

This ensures tests work on any architecture without modification.

## 🐛 Error Handling & Debugging

When tests fail:

1. **Collect Debug Information** via collect-kubernetes-logs action
2. **Create Failure Issue** with structured debugging data
3. **Preserve Artifacts** for offline analysis
4. **Graceful Cleanup** via cleanup-cluster action

## 🛠️ Development & Project Structure

### Project Layout

```
src/kube_galaxy/           # Main Python package
├── __main__.py            # CLI entry point
├── cli.py                 # Typer CLI dispatcher
├── cmd/                   # Command implementations
│   ├── validate.py        # Manifest/workflow validation
│   ├── test.py            # Test execution
│   ├── cleanup.py         # Cleanup operations
│   ├── setup.py           # Project initialization
│   └── status.py          # Project status display
└── pkg/                   # Business logic modules
    ├── manifest/          # YAML manifest handling
    │   ├── models.py      # Dataclasses for manifest structure
    │   ├── loader.py      # YAML → dataclass deserialization
    │   └── validator.py   # Schema validation
    ├── arch/              # Architecture detection
    │   └── detector.py    # Multi-arch support
    └── utils/             # Shared utilities
        ├── errors.py      # Custom exceptions
        ├── logging.py     # Colored output
        └── shell.py       # Subprocess wrapper

tests/                     # Test suite
├── unit/                  # Unit tests
│   ├── test_models.py     # Manifest model tests
│   ├── test_loader.py     # YAML loader tests
│   ├── test_validator.py  # Validation tests
│   └── test_arch.py       # Architecture mapping tests
└── functional/            # Functional/integration tests
```

### Task Automation with tox

All tasks are automated with `tox` for consistency:

```bash
# Run kube-galaxy CLI directly
tox -e kube-galaxy -- validate all
tox -e kube-galaxy -- status
tox -e kube-galaxy -- test local

# Run pytest test suite
tox -e test

# Run ruff linter/formatter
tox -e lint

# Run mypy type checker
tox -e type

# Build distribution
tox -e build

# List all available environments
tox list
```

### Direct CLI Usage

After installing the package, use `kube-galaxy` directly:

```bash
# Validation commands
kube-galaxy validate all              # Validate manifests
kube-galaxy validate manifests        # Validate only manifests

# Testing commands
kube-galaxy test local                # Local validation tests
kube-galaxy test spread               # Run spread tests against cluster
kube-galaxy test setup                # Create kubernetes cluster
kube-galaxy test-manifest <path>      # Inspect single manifest

# Cleanup commands
kube-galaxy cleanup all               # Clean files and clusters
kube-galaxy cleanup files             # Clean test artifacts
kube-galaxy cleanup clusters          # Remove kubernetes clusters

# Status and setup
kube-galaxy setup                     # Initialize project directories
kube-galaxy status                    # Show project status
kube-galaxy --version                 # Show CLI version
```

## 📋 Manifest Structure

1. Create a new manifest in `manifests/`:
   ```bash
   cp manifests/baseline-k8s-1.35.yaml manifests/my-cluster.yaml
   ```

2. Edit the manifest with your configuration

3. Validate it:
   ```bash
   kube-galaxy test-manifest manifests/my-cluster.yaml
   ```

### Adding New Components

1. In your component repository, create `spread.yaml` with:
   - `install` section with installation commands
   - `execute` section with test commands (if `use-spread: true`)

2. Reference the component in a cluster manifest:
   ```yaml
   components:
     - name: my-component
       release: "v1.0.0"
       repo: "https://github.com/myorg/my-component"
       use-spread: true
   ```

## 📚 References

- [Canonical Spread Testing Framework](https://github.com/canonical/spread)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Copilot Custom Instructions](.github/copilot-instructions.md)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [kubeadm Documentation](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/)

## 🤝 Contributing

1. Create a feature branch
2. Add or modify cluster manifests in `manifests/`
3. Add component references with proper repository structure
4. Validate with `tox -e kube-galaxy -- validate all` or `kube-galaxy validate all`
5. Run tests with `tox -e test`
6. Submit a pull request

The GitHub Actions workflows automatically test changes against the infrastructure.

---

**Note**: This infrastructure is designed for testing Kubernetes components at scale across multiple architectures. For production deployments, refer to official Kubernetes documentation.
