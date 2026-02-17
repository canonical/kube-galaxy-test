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

## 📋 Cluster Manifest Format

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
networking:
  - name: "calico"
    service-cidr: "10.96.0.0/12"
    pod-cidr: "192.168.0.0/16"
```

### Manifest Fields

- **name**: Unique cluster identifier
- **nodes**: Control plane and worker node counts
- **kubernetes-version**: Kubernetes version (informational)
- **components**: List of components to install
  - **name**: Component identifier
  - **release**: Git tag/branch to checkout
  - **repo**: Git repository URL
  - **use-spread**: If `true`, component repository provides spread tests
- **networking**: CNI and network settings

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

## 🚀 GitHub Actions Integration

The project uses GitHub Actions workflows for automated testing:

- **CI Triggers**: Pull requests run fast validation on `single-node-no-cni.yaml`
- **Manual Dispatch**: Baseline manifests run on manual `workflow_dispatch`
- **Test Automation**: Workflows invoke `kube-galaxy` CLI directly
- **Log Collection**: Failed runs preserve debug logs and cluster state

See `.github/workflows/` for workflow definitions and [.github/copilot-instructions.md](.github/copilot-instructions.md) for architecture details.

## 🏛️ Architecture Support

The infrastructure supports multiple CPU architectures:

| System | Kubernetes |
|--------|-----------|
| x86_64 | amd64 |
| aarch64 | arm64 |
| riscv64 | riscv64 |
| ppc64le | ppc64le |
| s390x | s390x |

**Runtime Detection**: Architecture is detected at startup via `uname -m` and automatically mapped to Kubernetes naming conventions. Components receive the mapped architecture for correct binary selection.

## 🐛 Debugging

When tests fail:

1. **Check logs**: Look at the test output and error messages
2. **Inspect cluster state**:
   ```bash
   kubectl get pods -A
   kubectl describe nodes
   ```
3. **Review preserved state**: Debug logs are collected before cleanup
4. **See manifests**: Use `kube-galaxy test-manifest` to inspect configurations

## 🛠️ Development & Project Structure

### Source Code Layout

```
src/kube_galaxy/
├── __main__.py            # CLI entry point
├── cli.py                 # Typer CLI dispatcher
├── cmd/                   # CLI command implementations
│   ├── validate.py        # Manifest validation
│   ├── test.py            # Test execution
│   ├── cleanup.py         # Cleanup operations
│   ├── setup.py           # Project initialization
│   └── status.py          # Project status
└── pkg/                   # Core business logic
    ├── manifest/          # YAML manifest parsing
    │   ├── models.py      # Dataclasses
    │   ├── loader.py      # YAML deserialization
    │   └── validator.py   # Schema validation
    ├── arch/              # Architecture detection
    │   └── detector.py    # uname → K8s mapping
    ├── cluster/           # Cluster provisioning
    │   └── setup.py       # Kubeadm-based setup
    ├── components/        # Component registry
    │   ├── _base.py       # Base component class
    │   ├── containerd.py  # Containerd component
    │   ├── kubeadm.py     # Kubeadm component
    │   └── *.py           # Other components
    ├── testing/           # Test execution
    │   └── spread.py      # Spread framework integration
    └── utils/             # Shared utilities
        ├── errors.py      # Custom exceptions
        ├── components.py  # Component utilities
        ├── logging.py     # Colored output
        ├── shell.py       # Subprocess wrapper
        ├── logs.py        # Log collection
        └── gh.py          # GitHub Actions integration
```

### Test Suite

```
tests/
├── unit/                  # Unit tests (35 tests)
│   ├── test_arch.py       # Architecture mapping
│   ├── test_loader.py     # Manifest parsing
│   ├── test_models.py     # Data structures
│   └── test_validator.py  # Validation logic
└── conftest.py            # Pytest configuration
```

### Core Modules Overview

| Module | Purpose |
|--------|---------|
| `pkg/cluster/setup.py` | Kubernetes cluster provisioning using kubeadm |
| `pkg/testing/spread.py` | Spread test framework integration |
| `pkg/manifest/loader.py` | YAML manifest parsing and deserialization |
| `pkg/manifest/validator.py` | Manifest schema and field validation |
| `pkg/arch/detector.py` | Runtime architecture detection and mapping |
| `pkg/utils/logs.py` | Kubernetes log collection for debugging |
| `pkg/utils/shell.py` | Safe subprocess execution wrapper |

## 📋 Manifest Authoring

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
