# Architecture Documentation

## Overview

Kubernetes Galaxy Test is a scalable, multiarch testing infrastructure for
Kubernetes components. It separates concerns into distinct phases:
cluster provisioning, component installation, and test execution.

## Design Principles

### 1. Component-Driven Architecture
- Each component (containerd, kubeadm, CNI, etc.) is defined in its own repository
- Components define their own installation instructions via `spread.yaml`
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
- **setup-cluster**: Provisions infrastructure
- **run-spread-tests**: Executes tests
- Each action is self-contained and reusable

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
│ 3. Install Components (setup-cluster)              │
│    For each component:                              │
│    • Download component from specified release     │
|    * Install and configure component               |
│    • Execute with ARCH, K_ARCH, RELEASE info       │
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
│ 5. Execute Tests (run-spread-tests)                │
│    • Identify components with test: true     │
│    • Clone component repos                          │
│    • Run spread tests from component spread.yaml   │
│    • Collect and report results                    │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│ 6. Cleanup (cleanup-cluster)                        │
│    • Drain and delete cluster resources             │
│    • Remove kubeconfig contexts                     │
│    • Cleanup temporary files                        │
└─────────────────────────────────────────────────────┘
```

## Component Repository Structure

A component repository providing custom installation must have `spread.yaml`:

```
my-component/
├── spread.yaml           # Required: optional test definitions
├── src/                  # Source code
```

### Component Awareness

Components receive architecture in environment:
- `ARCH`: The system architecture from `uname -m`
- `K_ARCH`: The Kubernetes-compatible architecture name

Components use this to download/build for the correct architecture.

## Custom GitHub Actions

### setup-cluster

**Input**: Cluster manifest path
**Output**: kubeconfig location, cluster info

**Steps**:
1. Detect system properties (architecture)
2. Install base dependencies
3. Parse manifest
4. install and configure each component
5. Initialize Kubernetes with kubeadm
6. Configure networking
7. Verify cluster health

**Key Features**:
- Runs as composite action (uses shell scripts)
- Fetches tools for detected architecture
- Invokes component install scripts
- Kubeadm-based cluster, not container-based

### run-spread-tests

**Input**: Manifest, test suite, timeout
**Output**: Test results, status

**Steps**:
1. Install spread testing framework
2. Scan manifest for test components
3. Clone component repos
4. Execute spread tests
5. Collect artifacts

**Key Features**:
- Tests come from components and local tests/
- Scans for test: true in components
- Reports results and failures
- Preserves test artifacts

### collect-kubernetes-logs

Gathers debugging information on failures:
- Node status and descriptions
- Pod logs and status
- Kubernetes events
- Network information
- System diagnostics

### create-failure-issue

Creates GitHub issues with:
- Failure context
- Debug information
- Links to artifacts
- Investigation steps

### cleanup-cluster

Graceful cluster teardown:
- Drain nodes
- Delete resources
- Remove kubeconfig entries
- Clean temporary files

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

## Testing Your Components

To develop a component for this infrastructure:

1. Create `spread.yaml` with `install` section
2. Test locally:
   ```bash
   export ARCH=$(uname -m)
   export K_ARCH="amd64"  # Example
   spread prepare
   spread execute
   spread restore
   ```

3. Add your repo to a cluster manifest
4. Test the full workflow in GitHub Actions

## Best Practices

1. **Keep components independent**: Component install shouldn't assume others are installed
2. **Support multiarch**: Provide binaries for amd64, arm64, riscv64
3. **Provide tests**: Use spread tests for quality assurance
4. **Document assumptions**: Note any OS, kernel, or runtime requirements
5. **Clean up after yourself**: Restore step should remove all test artifacts
6. **Use spread.yaml**: Standard format for component definitions

## Extension Points

### Adding New CNI Options
- Update setup-cluster's Configure Networking step
- Add case for your CNI in the switch

### Custom Networking
- Manifest supports multiple networking entries
- Update setup-cluster to handle your config

### New Storage Providers
- Add to manifest storage section
- setup-cluster can detect and install

### New Infrastructure Providers
- Currently supports GitHub Actions
- extend workflow generation for other providers
