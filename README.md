# Kubernetes Galaxy Test

![Kube-Galaxy-Test](docs/kube-galaxy.png "Kube Galaxy Tests")

A scalable, multi-architecture testing infrastructure for Kubernetes using
functional test suites that run on GitHub Actions. This project tests
custom-built Kubernetes components using the canonical
 [spread](https://github.com/canonical/spread) testing framework, with
 architecture detection and per-component test orchestration.

## 🏗️ Architecture

- **Python CLI**: Modern `kube-galaxy` command-line tool (Python 3.12+)
- **Cluster Manifests**: Simple YAML configuration files defining Kubernetes
  cluster setups with component lists
- **Per-Component Definition**: Each component specifies its repo, release,
  and whether it provides tests
- **GitHub Actions**: Automatic provisioning, testing, and cleanup workflows
- **Multiarch Support**: Runtime architecture detection
  (amd64, arm64, riscv64, etc.)
- **Component-Driven Tests**: Tests live in component repos, referenced via
  `test` flag
- **Kubeadm-Based Provisioning**: Real cluster setup without container-based
  shortcuts

## 🏃 Quick Start

### Prerequisites

- Python 3.12+ with `uv` or `pip`
- Git
- skopeo

### Development Setup

1. **Install uv tooling**:

   ```bash
   python3.12 -m pip install --user uv tox-uv
   ```

2. **Clone the repository**:

   ```bash
   git clone https://github.com/canonical/kube-galaxy-test.git
   cd kube-galaxy-test
   ```

3. **Create Python environment** (using `uv`):

   ```bash
   uv venv
   source .venv/bin/activate
   ```

   Or with `venv`:

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

4. **Install kube-galaxy with dev dependencies**:

   ```bash
   uv pip install -e .
   ```

### Basic Usage

1. **Validate the project**:

   ```bash
   kube-galaxy validate
   ```

2. **Setup the cluster**:

   ```bash
   kube-galaxy setup manifests/baseline-k8s-1.35.yaml
   ```

3. **Check project status**:

   ```bash
   kube-galaxy status
   ```

4. **Run tests**:

   ```bash
   # Run spread tests against active cluster
   kube-galaxy test manifests/baseline-k8s-1.35.yaml
   ```

## 📦 Available Manifests

The `manifests/` directory contains several pre-configured cluster definitions:

### Baseline Clusters (Run on `workflow_dispatch`)

- `baseline-k8s-1.33.yaml` - Full K8s 1.33 cluster
- `baseline-k8s-1.34.yaml` - Full K8s 1.34 cluster
- `baseline-k8s-1.35.yaml` - Full K8s 1.35 cluster
- `baseline-k8s-1.36.yaml` - Full K8s 1.36 cluster

These comprehensive manifests include full networking and are marked with
 `ci-skip-on-pr: "true"` to run only on manual workflow dispatch.

### Minimal Clusters (Run on PRs)

- `smoketest.yaml` - **Single-node cluster with CNI**
  - **Runs automatically on all PRs** for fast validation
  - Perfect for testing core Kubernetes components in isolation
  - Single control-plane node (no workers)

### CI Strategy

- **Pull Requests**: Fast validation with `smoketest.yaml` only (~5-10 minutes)
- **Workflow Dispatch**: Comprehensive testing with all manifests
  (~45-90 minutes per manifest)

**Example**: Testing the minimal cluster

```bash
# Inspect the manifest
kube-galaxy validate --manifest manifests/smoketest.yaml

# Setup the cluster
kube-galaxy setup manifests/smoketest.yaml

# Verify control plane is running
kubectl get pods -n kube-system
kubectl get nodes  # Will show NotReady status

# Clean up
kube-galaxy cleanup all
```

## 📋 Cluster Manifest Format

See [ARCHITECTURE](.github/ARCHITECTURE.md)

### Source-Format Placeholders

The `installation.source-format` field supports the following placeholders:

| Placeholder        | Resolves to                                                      |
|--------------------|------------------------------------------------------------------|
| `{{ arch }}`           | Kubernetes arch name (`amd64`, `arm64`, `riscv64`, …)           |
| `{{ release }}`        | Component release tag from the manifest                         |
| `{{ ref }}`            | Git ref override, or empty string                               |
| `{{ repo.base-url }}`  | Repository base URL; `local://path` expands to a `file://` URI rooted at cwd; `gh-artifact://name/path` routes to the GitHub Artifacts API |
| `{{ repo.subdir }}`    | Optional subdirectory within the repo (empty string if unset)   |
| `{{ repo.ref }}`       | Git ref from the `repo` block (empty string if unset)           |

**Example:**

```yaml
installation:
  method: binary-archive
  repo:
    base-url: "https://github.com/org/tool"
  source-format: "{{ repo.base-url }}/releases/download/v{{ release }}/tool-{{ release }}-linux-{{ arch }}.tar.gz"
```

### GitHub Actions Artifact Sources

A component whose test suite is uploaded as a GitHub Actions artifact in a
previous workflow step uses `base-url: gh-artifact://artifact-name` in its
`test.repo` block. The path after the artifact name in `source-format` locates
the file inside the downloaded zip.

```yaml
- name: mycomp
  category: example
  release: "1.2.3"
  installation:
    method: none
  test:
    method: spread
    repo:
      base-url: gh-artifact://mycomp-spread-artifact
      subdir: spread/kube-galaxy
    source-format: "{{ repo.base-url }}/{{ repo.subdir }}/task.yaml"
```

When `base-url` starts with `gh-artifact://`:

- `{{ repo.base-url }}` in `source-format` renders to the full
  `gh-artifact://artifact-name` URL; the path appended after it is the
  location of the file *inside* the artifact zip
- `download_file` dispatches the rendered URL to `gh_extract_artifact_file`,
  which calls the GitHub Artifacts REST API to find and download the zip,
  then extracts the requested file to the destination
- The `GITHUB_TOKEN` environment variable must be set (workflows provide this
  automatically via `${{ secrets.GITHUB_TOKEN }}`)
- The `GITHUB_REPOSITORY` environment variable must be set (set automatically
  in GitHub Actions)
- The feature only works inside a GitHub Actions workflow (`GITHUB_ACTIONS` must
  be set). Running locally will raise an error.

### Local Component Sources

A component whose test suite lives inside this repository uses `base-url: local://`
(or `base-url: local://relative/path`) in its `test.repo` block.  The
`source-format` template resolves to a `file://` URI rooted at the current
working directory.

```yaml
- name: mycomp
  category: example
  release: "1.2.3"
  installation:
    method: none
  test:
    method: spread
    repo:
      base-url: local://components/mycomp/
      subdir: spread/kube-galaxy
    source-format: "{{ repo.base-url }}/{{ repo.subdir }}/task.yaml"
```

When `base-url` starts with `local://`:

- `{{ repo.base-url }}` in `source-format` expands to a `file://` URI of cwd
  (optionally with the path fragment appended to cwd)
- The `download_hook` automatically copies the resolved local suite to the
  shared tests root so that spread can discover it

#### Local test structure

Test tasks for local components must exist at
`<cwd>/components/<name>/spread/kube-galaxy/task.yaml`:

```
components/
  mycomp/
    spread/
      kube-galaxy/
        task.yaml   ← spread task definition
```

Inside `task.yaml` you can reference environment variables set by kube-galaxy:

| Variable            | Description                                   |
|---------------------|-----------------------------------------------|
| `COMPONENT_VERSION` | Release tag from the manifest                 |
| `COMPONENT_NAME`    | Component name                                |
| `K8S_ARCH`          | Kubernetes architecture (`amd64`, `arm64`, …) |
| `SYSTEM_ARCH`       | Raw `uname -m` architecture                   |
| `IMAGE_ARCH`        | Container image architecture tag              |
| `KUBECONFIG`        | Path to shared kubeconfig                     |

Example `task.yaml`:

```yaml
summary: My component conformance test
execute: |
  wget --tries=3 https://example.com/releases/v${COMPONENT_VERSION}/tool_linux_${K8S_ARCH}.tar.gz \
      -O tool.tar.gz || exit 1
  tar -xvf tool.tar.gz
  ./tool --version
```

#### Adding a local component (the sonobuoy pattern)

1. Create `components/<name>/spread/kube-galaxy/task.yaml`
2. Add the component to the manifest with `test.method: spread`,
   `test.repo.base-url: local://`, and a `test.source-format` pointing to the
   local directory

#### Adding a gh-artifact component

1. Upload the spread test suite as a GitHub Actions artifact in an earlier
   workflow step (e.g. `actions/upload-artifact`)
2. Add the component to the manifest with `test.method: spread`,
   `test.repo.base-url: gh-artifact://artifact-name`, and a `test.source-format`
   that appends the internal zip path:

   ```yaml
   test:
     method: spread
     repo:
       base-url: gh-artifact://mycomp-spread-artifact
       subdir: spread/kube-galaxy
     source-format: "{{ repo.base-url }}/{{ repo.subdir }}/task.yaml"
   ```

3. Ensure `GITHUB_TOKEN` and `GITHUB_REPOSITORY` are available in the workflow
   environment (both are set automatically in GitHub Actions)

## 🔧 Component Repositories

Each component repository must contain a `spread.yaml` file that defines:

1. **Install instructions** (required if component is used)
2. **Test definitions** (required if `test.method: spread`)

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

- `SYSTEM_ARCH`: System architecture from `uname -m` (x86_64, aarch64, riscv64, etc.)
- `K8S_ARCH`: Kubernetes architecture name (amd64, arm64, riscv64, etc.)
- `IMAGE_ARCH`: Container image architecture tag (amd64, arm64, riscv64, etc.)
- `COMPONENT_VERSION`: The component version being installed
- `COMPONENT_REPO`: The repository URL

## 🚀 GitHub Actions Integration

The project uses GitHub Actions workflows for automated testing:

- **CI Triggers**: Pull requests run fast validation on `smoketest.yaml`
- **Manual Dispatch**: Baseline manifests run on manual `workflow_dispatch`
- **Test Automation**: Workflows invoke `kube-galaxy` CLI directly
- **Log Collection**: Failed runs preserve debug logs and cluster state

See `.github/workflows/` for workflow definitions and
[.github/copilot-instructions.md](.github/copilot-instructions.md)
for architecture details.

## 🏛️ Architecture Support

The infrastructure supports multiple CPU architectures:

| System | Kubernetes |
|--------|-----------|
| x86_64 | amd64 |
| aarch64 | arm64 |
| riscv64 | riscv64 |
| ppc64le | ppc64le |
| s390x | s390x |

**Runtime Detection**: Architecture is detected at startup via `uname -m` and
automatically mapped to Kubernetes naming conventions. Components receive the
mapped architecture for correct binary selection.

## 🐛 Debugging

When tests fail:

1. **Check logs**: Look at the test output and error messages
2. **Inspect cluster state**:

   ```bash
   kubectl get pods -A
   kubectl describe nodes
   ```

3. **Review preserved state**: Debug logs are collected before cleanup
4. **See manifests**: Inspect the YAML files in `manifests/` or run `kube-galaxy validate --manifest path/to/manifest.yaml` to validate a specific configuration

## � References

- [DEVELOPMENT.md](DEVELOPMENT.md) - Developer setup and workflow guide
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
5. Run tests with `tox -e unit`
6. Submit a pull request

The GitHub Actions workflows automatically test changes against the infrastructure.

---

**Note**: This infrastructure is designed for testing Kubernetes components at
scale across multiple architectures. For production deployments, refer to
official Kubernetes documentation.
