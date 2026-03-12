# Architecture Documentation

## Overview

Kubernetes Galaxy Test is a scalable, multiarch testing infrastructure for
Kubernetes components. It separates concerns into distinct phases:
cluster provisioning, component installation, and test execution.

## Design Principles

### 1. Component-Driven Architecture
- Each component (containerd, kubeadm, CNI, etc.) is defined in its own repository
- Components define their installation instructions via a `manifest/*.yaml`
- Components can optionally provide their own test suites
- The orchestration layer simply invokes component definitions

### 2. Multiarch from the Start
- All architecture-specific logic is handled at runtime
- No hardcoded binary paths or architecture names
- Tools and components are fetched for the detected architecture
- Architecture information is passed to component scripts

### 3. Simple Manifest Format
- Manifests use simple YAML (no Kubernetes resource types)
- Manifests declare what to install, not how to install it
- Complex Installation details can be defined as a component plugin
- Manifests can be validated without running anything

### 4. Separation of Concerns
- **kube-galaxy setup**: Provisions infrastructure
- **kube-galaxy test**: Executes tests
- **kube-galaxy status**: Cluster health checks
- **kube-galaxy cleanup**: Teardown and cleanup
- Each command is self-contained and reusable
- Commands implemented using Python with Typer CLI framework

## Workflow

```
┌─────────────────────────────────────────────────────┐
│ 1. Parse Cluster Manifest                           │
│    • Read component list, networking, storage config │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│ 2. Detect System Architecture                       │
│    • Determine runner arch (amd64, arm64, etc.)     │
│    • Map to Kubernetes arch names                   │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│ 3. Install Components (kube-galaxy setup)          │
│    For each component:                              │
│    • Download component from specified release     │
│    • Install and configure component               │
│    • Execute with SYSTEM_ARCH, K8S_ARCH, IMAGE_ARCH│
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│ 4. Initialize Kubernetes Cluster                    │
│    • Cluster with manifest networking config        |
│    • Deploy CNI plugin                              │
│    • Verify cluster health                          │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│ 5. Execute Tests (kube-galaxy test)                │
│    • Identify components with test.method: spread  │
│    • Discover spread test tasks                    │
│    • Execute tests in LXD containers via spread    │
│    • Collect and report results                    │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│ 6. Cleanup (kube-galaxy cleanup)                    │
│    • Drain and delete cluster resources             │
│    • Remove kubeconfig contexts                     │
│    • Cleanup temporary files                        │
└─────────────────────────────────────────────────────┘
```

## Adding Components

### Base Components (Manifest-Only)

Components that follow standard installation patterns can be defined purely in the manifest:

```yaml
# Example: Adding a binary component
- name: etcdctl
  category: etcd
  release: "3.5.0"
  installation:
    method: "binary-archive"
    repo:
      base-url: "https://github.com/etcd-io/etcd"
    source-format: "{{ repo.base-url }}/releases/download/v{{ release }}/etcd-v{{ release }}-linux-{{ arch }}.tar.gz"
    bin-path: "./etcd-v{{ release }}-linux-{{ arch }}/etcd"
```

**`source-format` placeholders**:

| Placeholder        | Resolves to                                                |
|--------------------|------------------------------------------------------------|
| `{{ arch }}`           | Kubernetes arch name (`amd64`, `arm64`, `riscv64`, …)     |
| `{{ release }}`        | Component release tag from the manifest                   |
| `{{ ref }}`            | Git ref override, or empty string                         |
| `{{ repo.base-url }}`  | Repository base URL, `cwd` for local sources, or artifact name for `gh-artifact` sources |
| `{{ repo.subdir }}`    | Optional subdirectory within the repo (empty if unset)    |
| `{{ repo.ref }}`       | Git ref from the `repo` block (empty if unset)            |

**Supported installation methods**:
- `binary`: Download direct binary artifacts
- `binary-archive`: Download and extract binary archives
- `container-image`: Pull and register container images
- `container-image-archive`: Pull and register container images from a tar
- `none`: Component installs nothing directly into the cluster (e.g. test-only)

### GitHub Actions Artifact Components

Components whose test suite is uploaded as a GitHub Actions artifact in a
previous workflow step use `base-url: gh-artifact` in their `test.repo` block.
The `source-format` template resolves to the **artifact name** queried via the
GitHub Artifacts REST API.

```yaml
- name: mycomp
  category: example
  release: "1.2.3"
  installation:
    method: none
  test:
    method: spread
    repo:
      base-url: gh-artifact
    source-format: "mycomp-spread-suite"
```

Requirements:
- `GITHUB_TOKEN` env var must be set (provided automatically in GHA workflows)
- `GITHUB_REPOSITORY` env var must be set (provided automatically in GHA workflows)
- The feature only works inside a GitHub Actions workflow context

The artifact is downloaded as a zip file to the component's temp directory.

### Local Components

Components whose test suite lives inside this repository use `base-url: local`
in their `test.repo` block.  The `source-format` template resolves to a path
under the current working directory.

```yaml
- name: sonobuoy
  category: vmware-tanzu/sonobuoy
  release: "0.57.3"
  installation:
    method: none
  test:
    method: spread
    repo:
      base-url: local
    source-format: "{{ repo.base-url }}/components/{{ name }}"
```

The corresponding task file must exist at:

```
components/
  sonobuoy/
    spread/
      kube-galaxy/
        task.yaml
```

The `download_hook` automatically copies the local suite (resolved via
`source-format`) to the shared tests root so that spread can discover it.

### Custom Components (Requires Python Class)

When components need special handling (complex configuration, multi-step bootstrap, dependencies), create a component class in `src/kube_galaxy/pkg/components/`:

```python
from kube_galaxy.pkg.components import ComponentBase, register_component

@register_component("mycomponent")
class MyComponent(ComponentBase):
    """My component description."""

    def download_hook(self) -> None:
        # Custom download logic
        pass

    def install_hook(self) -> None:
        # Custom install logic
        pass

    def configure_hook(self) -> None:
        # Configuration logic
        pass

    def bootstrap_hook(self) -> None:
        # Initialization logic
        pass
```

**When to use custom components**:
- Complex multi-step installation
- Runtime configuration generation (kubeadm, containerd)
- Service management (systemd)
- Dependencies on other components
- Bootstrap orchestration

**Available lifecycle hooks**: `download`, `pre_install`, `install`, `configure`, `bootstrap`, `verify`, `stop`, `delete`, `post_delete`

### Component Architecture Awareness

Components receive architecture information via environment variables:
- `SYSTEM_ARCH`: Raw system architecture from `uname -m` (e.g., x86_64, aarch64)
- `K8S_ARCH`: Kubernetes-compatible architecture name (e.g., amd64, arm64)
- `IMAGE_ARCH`: Container image architecture tag (e.g., amd64, arm64)

Components use these to download/build binaries and pull images for the correct architecture.

## Kube-Galaxy CLI Commands

The `kube-galaxy` CLI tool (built with Python and Typer) provides commands that are invoked in GitHub Actions workflows:

### kube-galaxy setup

**Usage**: `kube-galaxy setup <manifest-path>`

**Purpose**: Provision and configure a Kubernetes cluster

**Steps**:
1. Detect system architecture (SYSTEM_ARCH, K8S_ARCH, IMAGE_ARCH)
2. Parse cluster manifest
3. Execute component lifecycle hooks in order:
   - Download
   - Pre-install
   - Install (dependency-ordered)
   - Configure
   - Bootstrap (dependency-ordered)
   - Verify
4. Initialize Kubernetes cluster via a cluster-manager
5. Bootstrap remaining container based components
6. Verify cluster health

**Key Features**:
- Component plugin system with lifecycle hooks
- Dependency-based installation ordering
- Multiarch binary and image handling
- Cluster Management lifecycle manager is just another plugin

### kube-galaxy status

**Usage**: `kube-galaxy status`

**Purpose**: Display cluster health and status

**Output**:
- Cluster connectivity
- Node status
- System pod status
- Basic cluster info

### kube-galaxy test

**Usage**: `kube-galaxy test <manifest-path>`

**Purpose**: Execute spread tests for components whose `test.method` is `spread`

**Steps**:
1. Scan manifest for test-enabled components
2. Validate component test structure
3. Generate orchestration spread.yaml
4. Copy kubeconfig to shared directory (for LXD containers)
5. Create test namespace per component
6. Execute spread tests in isolated LXD containers
7. Collect and aggregate results
8. Cleanup test namespaces

**Key Features**:
- Spread framework integration for reproducible tests
- LXD container isolation
- Parallel test execution
- Automatic namespace management
- Test result aggregation

### kube-galaxy cleanup

**Usage**: `kube-galaxy cleanup all --manifest <manifest-path>`

**Purpose**: Graceful cluster teardown

**Steps**:
1. Parse manifest
2. Execute component teardown hooks in reverse order:
   - Stop (sequential)
   - Delete (sequential)
   - Post-delete (sequential)
3. Kubeadm reset
4. Remove cluster resources
5. Clean kubeconfig entries
6. Remove temporary files

**Key Features**:
- Best-effort cleanup (continues on errors)
- Component lifecycle hook support
- Complete cluster state removal

### GitHub Actions Integration

These CLI commands are invoked directly in GitHub Actions workflows:

```yaml
- name: Setup Cluster
  run: kube-galaxy setup manifests/my-cluster.yaml

- name: Run Tests
  run: kube-galaxy test manifests/my-cluster.yaml

- name: Cleanup
  if: always()
  run: kube-galaxy cleanup all --manifest manifests/my-cluster.yaml
```

Workflows handle:
- Debug log collection on failures
- Test result artifacts
- Issue creation for failures
- upterm debugging sessions

## Manifest Validation

Manifests are validated for:
- Valid YAML syntax
- Required fields present
- Component repos accessible
- Release tags exist
- spread.yaml exists in components

## Error Handling

### Component Installation Failures
- Logged and reported
- Workflow continues if optional
- Workflow stops if required

### Test Failures
- Tests continue even if one fails
- Results aggregated at end
- GitHub issue created automatically
- Debug information collected

### Cleanup Failures
- Cleanup attempts best-effort
- Errors logged but don't fail workflow
- Manual cleanup may be needed

## Developing Components

### Local Testing

1. **Create or modify manifest**: Add your component to a manifest file

2. **Test component installation**:
   ```bash
   # Install kube-galaxy CLI
   pip install -e .

   # Setup cluster with your component
   kube-galaxy setup manifests/my-test.yaml

   # Verify cluster health
   kube-galaxy status

   # Cleanup
   kube-galaxy cleanup all --manifest manifests/my-test.yaml
   ```

3. **Test component with spread tests** (if `test.method: spread`):
   ```bash
   # Ensure spread and LXD are installed
   go install github.com/snapcore/spread/cmd/spread@latest
   snap install lxd

   # Run tests
   kube-galaxy test manifests/my-test.yaml
   ```

### Creating Component Tests

Create spread test tasks in your component repository:

```
my-component-repo/
└── spread/
    └── kube-galaxy/
        └── basic/
            └── task.yaml
```

**task.yaml example**:
```yaml
summary: Test basic component functionality

details: |
    Verify the component is properly installed and functional

environment:
    COMPONENT_NAME: mycomponent

prepare: |
    # Setup test environment
    kubectl create namespace test-mycomponent

execute: |
    # Run test commands
    kubectl get pods -n test-mycomponent

restore: |
    # Cleanup
    kubectl delete namespace test-mycomponent
```

Environment variables available in tests:
- `SYSTEM_ARCH`: System architecture
- `K8S_ARCH`: Kubernetes architecture
- `IMAGE_ARCH`: Container image architecture
- `KUBECONFIG`: Path to kubeconfig
- `KUBE_GALAXY_NAMESPACE`: Test namespace
- `COMPONENT_NAME`: Component being tested
- `COMPONENT_VERSION`: Component release version

## Best Practices

1. **Keep components independent**: Component install shouldn't assume others are installed
2. **Support multiarch**: Provide binaries for amd64, arm64, riscv64
3. **Provide tests**: Use spread tests for quality assurance
4. **Document assumptions**: Note any OS, kernel, or runtime requirements
5. **Clean up after yourself**: Restore step should remove all test artifacts
6. **Use spread.yaml**: Standard format for component definitions

## Extension Points

### Adding New Cluster Manager Plugins

Create a custom component class in `src/kube_galaxy/pkg/components/`:

```python
@register_component("my-kube-maker")
class MyKubeMaker(ClusterComponentBase):

    def bootstrap_hook(self) -> None:
        # Apply bootstrap config
        pass
```

Add to manifest:
```yaml
components:
  - name: my-kube-maker
    category: kubernetes/kube-maker
    release: "1.0.0"
    installation:
      method: "binary-archive"
      repo:
        base-url: "https://github.com/org/my-kube-maker"
```

### Supporting New Architectures

Architecture detection and mapping is in `src/kube_galaxy/pkg/arch/detector.py`:
1. Add new architecture to mapping functions
2. Ensure components support the architecture
3. Test with `SYSTEM_ARCH` environment override
