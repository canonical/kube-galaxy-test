# Component Lifecycle Hook System - Design Document

## Problem Statement

The current component installation system is:
- Sequential and slow (no parallel downloads)
- Lacks dependency management
- Doesn't support custom binaries/images easily
- Has no structured lifecycle for complex setups

## Goals

1. **Parallel Downloads**: Download all binaries/images concurrently with connection pooling
2. **Proper Sequencing**: Execute installation stages in correct order based on dependencies
3. **Custom Binaries/Images**: Support custom URLs for binaries and container images
4. **Extensible**: Easy to add new components with complex requirements
5. **Clean API**: Class-based components with properties and instance attributes

**Note**: This is greenfield development - no backward compatibility needed.

## Architecture

### Component Lifecycle

```
┌─────────────┐
│  DOWNLOAD   │ ← Parallel execution (with connection pooling)
└──────┬──────┘
       │
┌──────▼───────┐
│ PRE_INSTALL  │ ← Machine preparation (swapoff, sysctl, etc.)
└──────┬───────┘
       │
┌──────▼───────┐
│   INSTALL    │ ← Install binaries/configs (dependency-ordered)
└──────┬───────┘
       │
┌──────▼───────┐
│  CONFIGURE   │ ← Configure Services
└──────────────┘
       │
┌──────▼───────┐
│  BOOTSTRAP   │ ← Start services (dependency-ordered)
└──────┬───────┘
```

### Key Design Decisions

1. **Class-Based Components**: Components inherit from `ComponentBase`
   - Pros: Declarative, easy access to manifest/config, Pythonic
   - Instance attributes for state management
   - Properties for configuration access

2. **Component Registration**: Decorator pattern at class definition
   - Pros: Simple, declarative, self-documenting
   - `@register_component_class` decorator

3. **Dependency Graph**: Manifest model handles dependency resolution
   - Pros: Clear separation of concerns, testable
   - Cons: Must be computed before execution

4. **No Backward Compatibility**: Greenfield development
   - Pros: Clean codebase, no legacy baggage
   - Focus on best practices and modern Python idioms

## Data Flow

### 1. Manifest Loading
```python
manifest = load_manifest("cluster.yaml")
# Returns: [runc, containerd, kubelet, kubeadm]
```

### 2. Component Discovery
```python
# Get registered component class
component_class = get_component_class(component.name)

# Create instance with manifest context
component_instance = create_component_instance(
    component.name,
    manifest,
    component
)
# Instance has: self.manifest, self.component, and all properties
```

### 3. Stage Execution
```python
# For each component, create instance
instances = [
    create_component_instance(comp.name, manifest, comp)
    for comp in components
]

# Stage 1: Download (parallel)
await asyncio.gather(*[
    instance.download_hook(
        comp.repo, comp.release, comp.format, arch
    )
    for instance, comp in zip(instances, components)
])

# Stages 2-6: Sequential (respecting dependencies)
for stage in ['pre_install', 'install', 'bootstrap', 'post_bootstrap', 'configure']:
    for instance in instances:
        hook = getattr(instance, f'{stage}_hook')
        hook()  # Call the hook method
```

## Implementation Phases

### ✅ Phase 1: Infrastructure (COMPLETED)
- [x] Define `ComponentHooks` dataclass
- [x] Define `HookStage` enum
- [x] Implement hook registry
- [x] Update manifest models for dependencies
- [x] Implement dependency sorting algorithm
- [x] Update kubeadm and containerd as examples
- [x] Create documentation

### 🚧 Phase 2: Component Migration (IN PROGRESS)
- [ ] Update remaining component modules with hooks
  - [ ] runc
  - [ ] kubelet
  - [ ] kubectl
  - [ ] etcd
  - [ ] etcdctl
  - [ ] coredns
  - [ ] kube-proxy
  - [ ] kube-apiserver
  - [ ] kube-controller-manager
  - [ ] kube-scheduler
  - [ ] pause
  - [ ] cni-plugins
- [ ] Define dependencies for each component
- [ ] Set appropriate priorities

### 📋 Phase 3: Execution Engine
- [ ] Create staged execution orchestrator in `cluster/setup.py`
- [ ] Implement parallel download with connection pooling
- [ ] Add progress reporting for each stage
- [ ] Implement error handling and rollback
- [ ] Add timeout configuration per stage

### 📋 Phase 4: Custom Binary/Image Support
- [ ] Support `custom_binary_url` in manifest
- [ ] Support `custom_image_url` in manifest
- [ ] Update download hooks to check for custom URLs first
- [ ] Add validation for custom URLs

### 📋 Phase 5: Advanced Features
- [ ] Hook timeout configuration
- [ ] Retry logic for downloads
- [ ] Parallel execution within stages (where safe)
- [ ] Hook result caching
- [ ] Dry-run mode

### 📋 Phase 6: Testing & Polish
- [ ] Unit tests for hook system
- [ ] Integration tests for full cluster setup
- [ ] Update existing manifests with dependencies
- [ ] Performance benchmarks (parallel vs sequential)
- [ ] Complete documentation with examples


## Manifest Example

```yaml
name: custom-cluster
kubernetes-version: "1.35.0"

components:
  # Container runtime foundation
  - name: runc
    release: "1.3.4"

  - name: containerd
    release: "2.2.1"
    installation:
      method: "binary-archive"
      source_format: "https://custom-mirror.example.com/containerd-{version}.tar.gz"

  # Kubernetes core
  - name: kubelet
    release: "1.35.0"

  - name: kubeadm
    release: "1.35.0"
```

## Performance Expectations

### Before (Sequential)
```
Download runc:       10s
Download containerd: 15s
Download kubelet:    20s
Download kubeadm:    15s
Total download:      60s

Install all:         30s
Total:              ~90s
```

### After (Parallel Downloads)
```
Download all:        20s (parallel, limited by slowest)
Install all:         30s
Total:              ~50s

Speedup:            ~45% faster
```

## Security Considerations

1. **Custom URLs**: Validate HTTPS, check checksums if provided
2. **Download verification**: Verify signatures where available
3. **Privilege escalation**: Some hooks require root, document this
4. **State isolation**: Module state not shared between components

## Future Enhancements

1. **Plugin System**: Allow external hooks without modifying core code
2. **Remote Execution**: Run hooks on remote nodes
3. **Container-based Execution**: Run hooks in isolated containers
4. **State Persistence**: Save hook execution state for resume
5. **Distributed Installation**: Coordinate across multiple machines

## References

- ChatGPT conversation: https://chatgpt.com/share/698f49ba-276c-8000-aa4b-275a1a42d996
- Kubernetes setup guide: https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/
- Component lifecycle patterns: https://kubernetes.io/docs/concepts/overview/components/
