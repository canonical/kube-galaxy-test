# Kubernetes Galaxy Test - Quick Reference

## Installation

```bash
# Clone repository
git clone https://github.com/canonical/kube-galaxy-test.git
cd kube-galaxy-test

# Setup Python environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install kube-galaxy
pip install -e ".[test,lint,type]"

# Or with uv (faster)
uv venv
source .venv/bin/activate
uv pip install -e ".[test,lint,type]"
```

## CLI Commands

### Validation
```bash
kube-galaxy validate all          # Validate everything
kube-galaxy validate manifests    # Validate YAML manifests
kube-galaxy validate workflows    # Validate GitHub Actions
```

### Testing
```bash
kube-galaxy test local            # Local validation tests
kube-galaxy test spread           # Run spread tests
kube-galaxy test setup            # Setup cluster from manifest
kube-galaxy test-manifest FILE    # Inspect manifest
```

### Management
```bash
kube-galaxy setup                 # Initialize project
kube-galaxy cleanup all           # Clean artifacts
kube-galaxy cleanup files         # Clean test artifacts
kube-galaxy cleanup clusters      # Remove test clusters
kube-galaxy status                # Project status
kube-galaxy --version             # Show version
```

## Tox Commands

```bash
# List all environments
tox list

# Run specific environment
tox -e test               # Run pytest
tox -e lint               # Run ruff
tox -e type               # Run mypy
tox -e build              # Build distribution

# Passthrough CLI
tox -e kube-galaxy -- validate all
tox -e kube-galaxy -- test-manifest manifests/baseline-k8s-1.35.yaml
```

## Project Structure

```
src/kube_galaxy/
├── cli.py                  # CLI entry point (Typer)
├── cmd/                    # CLI command handlers
│   ├── validate.py
│   ├── test.py
│   ├── cleanup.py
│   ├── setup.py
│   └── status.py
└── pkg/                    # Business logic
    ├── manifest/           # Manifest loading/validation
    ├── arch/               # Architecture detection
    ├── cluster/            # Cluster setup (setup.py)
    ├── testing/            # Test execution (spread.py)
    └── utils/              # Shared utilities (logs.py)

tests/
├── unit/                   # Unit tests (35 tests)
│   ├── test_models.py
│   ├── test_loader.py
│   ├── test_validator.py
│   └── test_arch.py
└── functional/             # Functional tests

manifests/                  # Cluster definitions
├── baseline-k8s-1.33.yaml
├── baseline-k8s-1.34.yaml
├── baseline-k8s-1.35.yaml
└── baseline-k8s-1.36.yaml
```

## Key Modules

### `pkg/cluster/setup.py`
Kubernetes cluster provisioning using kubeadm.
- `setup_cluster()` - Main entry point
- Architecture detection and component installation
- Kubeadm initialization and health verification

### `pkg/testing/spread.py`
Spread test framework integration and execution.
- `run_spread_tests()` - Execute tests
- `collect_test_results()` - Gather results

### `pkg/utils/logs.py`
Kubernetes log collection for debugging.
- `collect_kubernetes_logs()` - Collect all logs
- `create_debug_issue()` - Generate Markdown summary

### `pkg/manifest/`
YAML manifest handling.
- `models.py` - Dataclasses for cluster configuration
- `loader.py` - YAML → dataclass deserialization
- `validator.py` - Schema and field validation

### `pkg/arch/`
Multi-architecture support.
- `detector.py` - Runtime architecture mapping

## Development Workflow

### 1. Validate Changes
```bash
kube-galaxy validate all
# or
tox -e kube-galaxy -- validate all
```

### 2. Run Tests
```bash
tox -e test
# With coverage
tox -e test -- --cov
```

### 3. Check Code Quality
```bash
tox -e lint     # Linting and formatting
tox -e type     # Type checking
```

### 4. Build Distribution
```bash
tox -e build
```

## Manifest Example

```yaml
name: baseline-k8s-1.35
description: "Kubernetes 1.35 baseline cluster"
kubernetes-version: "1.35.0"

nodes:
  control-plane: 1
  worker: 2

components:
  - name: containerd
    category: containerd
    release: "2.1.0"
    repo: "https://github.com/containerd/containerd"
    format: "Binary"
    use-spread: false

  - name: etcd
    category: etcd
    release: "v3.5.9"
    repo: "https://github.com/etcd-io/etcd"
    format: "Binary"
    use-spread: false

networking:
  - name: default
    service-cidr: "10.96.0.0/12"
    pod-cidr: "192.168.0.0/16"
```

## Troubleshooting

### Tests failing
```bash
# Check Python version
python --version  # Should be 3.12+

# Clear tox cache
tox -r -e test

# Run with verbose output
tox -e test -- -vv
```

### Import errors
```bash
# Reinstall in development mode
pip install -e . --no-deps

# Or with uv
uv pip install -e . --no-deps
```

### Manifest validation failing
```bash
# Inspect manifest details
kube-galaxy test-manifest manifests/baseline-k8s-1.35.yaml

# Validate YAML syntax
yq eval '.' manifests/baseline-k8s-1.35.yaml
```

## References

- [README.md](README.md) - Full documentation
- [Copilot Instructions](.github/copilot-instructions.md) - Project guidelines
- [Migration Report](MIGRATION_COMPLETE.md) - Completion details
- [Canonical Spread](https://github.com/canonical/spread) - Testing framework
- [Kubernetes Docs](https://kubernetes.io/) - K8s reference

---

**Last Updated**: February 12, 2026
**Python Version**: 3.12+
**Status**: Production Ready ✅
