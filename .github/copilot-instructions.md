# Kubernetes Galaxy Test - Copilot Instructions

## Project Overview
Scalable Kubernetes testing infrastructure that validates custom-built components (kubeadm, containerd, etc.) across multiple Kubernetes versions (1.33-1.36) on multiarch systems (amd64, arm64, riscv64, etc.) using Python CLI and portable modules. Tests use canonical [spread](https://github.com/canonical/spread) framework from component repositories.

## Core Architecture

**Manifest-Driven Design** - YAML cluster configurations:
- Define K8s version, node counts, networking, and component versions/sources
- Components specify repo URL, release tag, format (Binary|Container|Binary+Container), and `test` flag (component provides tests)
- 4 baseline manifests targeting K8s 1.33, 1.34, 1.35, 1.36 with 30+ components each (containerd, etcd, coredns, kube-* etc.)

**Python CLI Framework** - Cross-platform testing:
- `kube-galaxy` CLI with command routing and automatic manifest discovery
- `pkg/cluster/setup.py`: Manifest-based provisioning via kubeadm (not container shortcuts)
- `pkg/testing/spread.py`: Executes spread tests from components marked `test: true`
- `pkg/utils/logs.py`: Log collection and debugging utilities
- Library utilities for arch detection, YAML manifest parsing, component installation

**Multiarch Support Built In**:
- Runtime arch detection with mapping to K8s binary formats (amd64, arm64, riscv64, arm, ppc64le, s390x)
- Components receive SYSTEM_ARCH, K8S_ARCH, IMAGE_ARCH environment variables
- Container image tags mapped per architecture (e.g., aarch64→arm64)

**GitHub Actions Integration**:
- Single workflow matrix tests across all K8s versions with customizable runner sizes
- Uses astral-sh/setup-uv for fast Python environment setup
- Direct CLI invocation with no custom action wrappers needed
- Automatic debug log collection and issue creation on failures

## Development & Testing Commands

These commands mirror the CI workflows in `.github/workflows/` exactly.

**Prerequisites** (one-time):
```bash
# Install tox with uv backend (matches CI setup in .github/workflows/*.yml)
uv tool install tox --with tox-uv
```

**Available tox environments** (defined in `tox.ini`):
| Command | What it runs | CI workflow |
|---|---|---|
| `tox -e unit` | pytest with coverage (`tests/`) | `.github/workflows/test.yml` |
| `tox -e lint` | ruff check + mypy --strict | `.github/workflows/lint.yml` |
| `tox -e format` | ruff format + ruff check --fix (autoformat) | — |
| `tox -e build` | Build wheel and sdist | — |

**Before committing — always run:**
```bash
tox -e lint,unit
```

**Run all environments:**
```bash
tox
```

> **Note**: There is no `tox -e test` or `tox -e type` environment. Use `tox -e unit` for tests and `tox -e lint` for type checking (mypy runs as part of lint).

## Essential Workflows & Patterns

### Manifest Anatomy
```yaml
name: baseline-k8s-1.35           # Cluster identifier
description: "1.35.0 baseline"    # Human-readable
kubernetes-version: "1.35.0"       # Reference only
nodes:
  control-plane: 1                # Kubeadm provisioning count
  worker: 2
components:
  - name: containerd              # Component identifier
    category: containerd           # Organizational
    release: "2.2.1"              # Git tag or branch
    repo:                          # Repository info object
      base-url: "https://github.com/..."  # Required: fetch source
      subdir: "path/to/component"  # Optional: for monorepo components
      ref: "feature-branch"        # Optional: override release with git ref
    format: Binary|Container|Binary+Container  # Install method
    test: false/true        # Component provides spread tests
networking:
  - name: calico
    service-cidr: "10.96.0.0/12"
    pod-cidr: "192.168.0.0/16"
```
Key insight: `test: true` means component repo has spread.yaml tests that `kube-galaxy test` will execute.

### Local Development Workflow
```bash
# Validate manifest YAML syntax
kube-galaxy validate

# Provision real cluster with kubeadm (no container shortcuts)
kube-galaxy setup

# Run spread tests from components with test: true
kube-galaxy test spread

# Clean cluster and artifacts
kube-galaxy cleanup all
```

### CI/CD Test Execution
- **Single matrix workflow**: `test-baseline-clusters.yml` tests all K8s versions (1.33-1.36) in parallel
- **Inputs**: manifest path, K8s version (matrix param), test suite name
- **Process**: setup → run tests → collect logs on failure → cleanup (always)
- **Failure handling**: Custom action `create-failure-issue` captures full debug state (pods, nodes, events) in issue body
- **Artifact retention**: 30 days for test results

### Component Installation Pattern
`pkg/cluster/setup.py` provides the standard flow:
1. Fetch component repo at specified release tag (git clone + git checkout)
2. Locate installation method: `spread.yaml` → extract install script path
3. Validate architecture compatibility (SYSTEM_ARCH, K8S_ARCH, IMAGE_ARCH env vars)
4. Execute install script, verify binary in PATH
5. Components specify format: Binary (install to /usr/local/bin), Container (pull image), or both

### Test Execution Model
- **Test discovery**: Only components with `test: true` are tested
- **Test location**: Component repos contain `spread.yaml` at root
- **Spread execution**: `kube-galaxy test spread` clones each component, finds spread.yaml, runs spread test suite
- **Parallelism**: Spread tests run concurrently if specified in spread.yaml
- **Test results**: Captured and uploaded as GitHub artifacts

### Multiarch Execution
Architecture detection happens at runtime in `pkg/cluster/setup.py`:
- Calls `get_arch_info()` from `pkg/arch/detector.py`
- Sets: `SYSTEM_ARCH` (raw uname), `K8S_ARCH` (Kubernetes format), `IMAGE_ARCH` (container tag format)
- All component install scripts receive these three env vars for architecture-specific behavior
- Example: aarch64 system → K8S_ARCH=arm64, IMAGE_ARCH=arm64

## Critical Design Patterns

**State Preservation for Debugging**:
- Cluster state saved to `debug-logs/` directory before cleanup
- Preserve: kubectl dump, pod logs, events, node descriptions
- GitHub Actions auto-creates failure issues with this debug data
- Files survive cleanup and kubeadm reset for post-failure investigation

**Manifest as Single Source of Truth**:
- All behavior (components, versions, networking) defined in YAML manifests
- No hardcoding component lists or versions in Python code
- Each K8s version has its own manifest: baseline-k8s-1.33.yaml through 1.36.yaml
- Python modules parse manifests using `pkg/manifest/loader.py`

**Module Organization**:
- `pkg/arch/detector.py`: Pure architecture detection/mapping (no side effects)
- `pkg/manifest/loader.py`: Pure YAML parsing/extraction (no modifications)
- `pkg/manifest/validator.py`: Schema and field validation
- `pkg/cluster/setup.py`: Cluster setup operations
- `pkg/testing/spread.py`: Test execution
- CLI commands in `cmd/` compose these modules for user-facing behavior

**Error Handling & Cleanup**:
- `kube-galaxy setup`: Creates cluster, exits on first error (fail-fast)
- `kube-galaxy cleanup all`: Always runs `kubeadm reset --force`, removes artifacts
- GitHub Actions use `if: always()` to ensure cleanup even on failures

## GitHub Actions Integration

**Current Implementation**:
- **Setup Python**: Uses astral-sh/setup-uv@v7.2.1 for fast environment setup
- **Install CLI**: `pip install -e .` installs kube-galaxy CLI
- **Run Commands**: Direct invocation of `kube-galaxy` CLI commands
- **Failure Handling**: Automatic log collection via `pkg/utils/logs.py`
- **Artifact retention**: 30 days for test results

**Implementation Pattern**:
- Workflow defined in `.github/workflows/test-baseline-clusters.yml`
- Calls Python CLI directly; CLI provides GitHub logging integration
- No external action dependencies needed
- All features (setup, test, logs) provided by Python modules

## Best Practices

**When Adding Components**:
1. Add entry to all 4 `manifests/baseline-k8s-*.yaml` files (don't skip versions)
2. Set `test: true` only if component repo has `spread.yaml` with test definitions
3. Use canonical GitHub repos where available; verify release tag exists
4. Set `format` correctly based on component's build/distribution (Binary, Container, or both)

**When Modifying Python Modules**:
1. Follow existing patterns in `pkg/` modules for business logic
2. Use `pkg/utils/errors.py` custom exceptions for error handling
3. Test locally with `tox -e lint,unit` before committing
4. Update docstrings and type hints for all functions
5. Use manifest parsing (`load_manifest()` from loader) instead of hardcoding

**When Debugging Failures**:
1. Check `debug-logs/` directory for preserved cluster state BEFORE cleanup removes it
2. View GitHub Actions artifact logs from failure runs (30-day retention)
3. Verify SYSTEM_ARCH/K8S_ARCH/IMAGE_ARCH env vars in manifest detection
4. Run `kube-galaxy cleanup all` manually if workflow fails mid-setup for cleanup

## CLI Command Reference

```bash
# Validation
kube-galaxy validate
kube-galaxy validate --manifest manifests/baseline-k8s-1.35.yaml

# Testing
kube-galaxy setup manifests/baseline-k8s-1.35.yaml
kube-galaxy test manifests/baseline-k8s-1.35.yaml

# Management
kube-galaxy cleanup manifests/baseline-k8s-1.35.yaml
kube-galaxy status
```

## Integration References
- [GitHub Copilot Custom Agents](https://docs.github.com/en/copilot/tutorials/customization-library/custom-agents/your-first-custom-agent)
- [Canonical Spread Testing](https://github.com/canonical/spread)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

## Quick Start Commands
```bash
# Generate new cluster manifest
copilot: "Create a new cluster manifest for testing with 5 worker nodes and custom containerd version"

# Create GitHub Action workflow
copilot: "Generate a GitHub Actions workflow for the high-availability cluster manifest"

# Add error handling
copilot: "Add comprehensive error handling and issue creation to the existing workflow"

# Create test suite
copilot: "Create a spread test suite for networking functionality"
```

---

This project leverages GitHub Copilot to accelerate development of scalable Kubernetes testing infrastructure. Follow these instructions to ensure consistent, robust, and maintainable test automation.
