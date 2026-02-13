# Component Lifecycle Hook System - Planning Summary

> **⚠️ NOTE**: This document contains historical planning information. 
> For current implementation, see:
> - `docs/class-based-components.md` - Current API guide
> - `docs/component-lifecycle-hooks.md` - Hook system overview  
> - `IMPLEMENTATION_COMPLETE.md` - Final implementation status
>
> **Key Changes from Planning**:
> - ✅ Class-based components (not function-based)
> - ✅ Properties instead of getter methods
> - ✅ Instance attributes instead of state dict
> - ✅ No backward compatibility (greenfield)

## What We've Accomplished

We've designed and implemented the foundation for a comprehensive component lifecycle hook system that addresses the requirements from the ChatGPT conversation about custom images and binaries.

### ✅ Completed Implementation (Phase 1)

#### 1. Core Infrastructure
**File**: `src/kube_galaxy/pkg/components/__init__.py`

- **`HookStage` Enum**: Defines 6 lifecycle stages
  - `DOWNLOAD`: Parallel downloads with pooling
  - `PRE_INSTALL`: Machine preparation (swapoff, sysctl)
  - `INSTALL`: Install binaries/configs
  - `BOOTSTRAP`: Start services, run kubeadm init
  - `POST_BOOTSTRAP`: Get kubeconfig, post-init tasks
  - `CONFIGURE`: Final verification

- **`ComponentHooks` Dataclass**: Component lifecycle definition
  - Optional hook functions for each stage
  - Dependencies list (e.g., kubeadm depends on containerd, kubelet)
  - Priority for ordering (lower = earlier)
  - Metadata (name, category)

- **Hook Registry**: Global component hook management
  - `register_component_hooks()`: Components self-register
  - `get_component_hooks()`: Retrieve hooks for execution
  - Automatic discovery at module import time

#### 2. Enhanced Data Models
**File**: `src/kube_galaxy/pkg/manifest/models.py`

- **Updated `Component` Model**:
  - `dependencies`: List of required components
  - `priority`: Execution order (default: 50)
  - `custom_binary_url`: Override default binary URL
  - `custom_image_url`: Override default image URL
  - `skip_hooks`: Disable specific hooks
  - `hook_config`: Hook-specific configuration

- **Updated `Manifest` Model**:
  - `get_components_by_priority()`: Topological sort
  - Dependency resolution algorithm
  - Validates no circular dependencies
  - Returns components in correct execution order

#### 3. Example Implementations
**Files**: `kubeadm.py`, `containerd.py`

Both components now have:
- Separate `download_hook` and `install_hook`
- Module-level state to pass data between hooks
- `bootstrap_hook` to start services
- `post_bootstrap_hook` for kubeadm (get kubeconfig)
- `configure_hook` for verification
- Proper dependency declarations
- Legacy API wrappers for backward compatibility

**Example - kubeadm**:
```python
_kubeadm_hooks = ComponentHooks(
    name="kubeadm",
    category="kubernetes/kubernetes",
    download=download_hook,
    install=install_hook,
    bootstrap=bootstrap_hook,
    post_bootstrap=post_bootstrap_hook,
    configure=configure_hook,
    dependencies=["containerd", "kubelet"],
    priority=30,
)
register_component_hooks(_kubeadm_hooks)
```

#### 4. Documentation
**Files**: `docs/component-lifecycle-hooks.md`, `docs/hook-system-design.md`

- User guide for hook system
- Design document with architecture
- Implementation roadmap
- Component dependency map
- Performance analysis
- Security considerations

### 🎯 Design Principles

1. **Separation of Concerns**: Each hook handles one stage
2. **Dependency-Driven**: Execution order based on dependencies
3. **Parallel Where Possible**: Downloads run concurrently
4. **Backward Compatible**: Existing code still works
5. **Extensible**: Easy to add new components
6. **Testable**: Pure functions, clear interfaces

### 📊 Expected Benefits

1. **Performance**: ~45% faster setup via parallel downloads
2. **Flexibility**: Custom binaries/images easily supported
3. **Reliability**: Proper sequencing prevents race conditions
4. **Maintainability**: Clear structure, self-documenting
5. **Extensibility**: New components follow established pattern

## What's Next

### Phase 2: Component Migration (Next Priority)

Update remaining 11 component modules:
- runc, kubelet, kubectl
- etcd, etcdctl, coredns
- kube-proxy, kube-apiserver, kube-controller-manager, kube-scheduler
- pause, cni-plugins

Each needs:
- Hook functions for relevant stages
- Dependency declarations
- Priority assignment
- Hook registration

### Phase 3: Execution Engine

Create `cluster/lifecycle.py` orchestrator:
```python
class LifecycleOrchestrator:
    def execute_stage(self, stage: HookStage, components: list[Component]):
        """Execute a lifecycle stage for all components."""
        
    async def parallel_downloads(self, components: list[Component]):
        """Download all components in parallel with pooling."""
        
    def execute_sequential(self, stage: HookStage, components: list[Component]):
        """Execute stage sequentially in dependency order."""
```

Update `cluster/setup.py` to use orchestrator:
```python
def setup_cluster(manifest_path: str, ...):
    manifest = load_manifest(manifest_path)
    components = manifest.get_components_by_priority()
    
    orchestrator = LifecycleOrchestrator(components)
    
    # Execute stages
    await orchestrator.parallel_downloads()
    orchestrator.execute_stage(HookStage.PRE_INSTALL)
    orchestrator.execute_stage(HookStage.INSTALL)
    orchestrator.execute_stage(HookStage.BOOTSTRAP)
    orchestrator.execute_stage(HookStage.POST_BOOTSTRAP)
    orchestrator.execute_stage(HookStage.CONFIGURE)
```

### Phase 4: Custom Binary/Image Support

Update download hooks to check manifest:
```python
def download_hook(repo: str, release: str, format: str, arch: str) -> None:
    # Check for custom URL from manifest
    component = get_current_component()
    url = component.custom_binary_url or construct_default_url(...)
    download_file(url, ...)
```

### Phase 5: Advanced Features

- Connection pooling for downloads
- Progress bars for long operations
- Timeout configuration per hook
- Retry logic with exponential backoff
- Dry-run mode for testing

### Phase 6: Testing & Polish

- Unit tests for all hooks
- Integration tests for full setup
- Performance benchmarks
- Update all manifests with dependencies
- Final documentation polish

## How to Use (Future State)

### Manifest with Dependencies and Install Methods
```yaml
components:
  # Binary with tar.gz archive extraction
  - name: runc
    release: "1.3.4"
    priority: 5
    install_method: binary-archive
    archive_format: tar.gz
    
  # Binary archive with custom URL
  - name: containerd
    release: "2.2.1"
    dependencies: [runc]
    priority: 10
    install_method: binary-archive
    archive_format: tar.gz
    custom_binary_url: "https://custom-mirror.com/containerd-2.2.1.tar.gz"
    
  # Direct binary download (no extraction)
  - name: kubectl
    release: "1.35.0"
    priority: 20
    install_method: binary-direct
    custom_binary_url: "https://dl.k8s.io/release/v1.35.0/bin/linux/amd64/kubectl"
    
  # Kubeadm with custom bootstrap timeout
  - name: kubeadm
    release: "1.35.0"
    dependencies: [containerd, kubelet]
    priority: 30
    install_method: binary-direct
    skip_hooks: [bootstrap]  # Manual cluster init
    hook_config:
      bootstrap:
        pod_network_cidr: "10.244.0.0/16"
        
  # Helm chart deployment with custom image
  - name: calico
    release: "3.27.0"
    priority: 40
    install_method: helm-chart
    helm_chart_url: "https://projectcalico.docs.tigera.io/charts"
    custom_image_url: "registry.example.com/calico/node:v3.27.0"
    helm_values:
      installation:
        cni:
          type: Calico
        calicoNetwork:
          ipPools:
            - cidr: 192.168.0.0/16
              
  # Pod manifest deployment
  - name: coredns
    release: "1.11.0"
    priority: 45
    install_method: pod-manifest
    manifest_url: "https://example.com/manifests/coredns-1.11.0.yaml"
    manifest_type: deployment
```

### Creating a New Component
```python
# components/mycomponent.py
from kube_galaxy.pkg.components import ComponentHooks, register_component_hooks

_state = {}

def download_hook(repo, release, format, arch):
    # Download logic, store in _state
    pass

def install_hook(repo, release, format, arch):
    # Install from _state
    pass

_hooks = ComponentHooks(
    name="mycomponent",
    category="tools",
    download=download_hook,
    install=install_hook,
    dependencies=["otherthing"],
    priority=25,
)
register_component_hooks(_hooks)
```

## Questions for Discussion

### Answered and Implemented ✅

1. **Connection Pooling**: How many concurrent downloads?
   - **Answer**: 5 concurrent downloads
   - **Implementation**: `DOWNLOAD_POOL_SIZE = 5` in `constants.py`

2. **Timeout Values**: Default timeouts per stage?
   - **Answer**: Custom timeouts per component, defined as module-level constants
   - **Implementation**: 
     - Default timeouts in `constants.py`
     - Component-specific constants (e.g., `kubeadm.BOOTSTRAP_TIMEOUT = 600`)
     - `ComponentHooks.get_timeout(stage)` method
   - **Defaults**:
     - DOWNLOAD: 300s (5 min)
     - PRE_INSTALL: 60s (1 min)
     - INSTALL: 120s (2 min)
     - BOOTSTRAP: 300s (5 min)
     - POST_BOOTSTRAP: 60s (1 min)
     - CONFIGURE: 60s (1 min)

3. **Error Handling**: Retry logic or fail-fast?
   - **Answer**: Fail-fast (no retries for now)
   - **Implementation**: `FAIL_FAST = True` in `constants.py`

4. **Installation Methods**: How to handle different binary/container types?
   - **Answer**: Extensible `install_method` field in Component model
   - **Implementation**:
     - `InstallMethod` enum with multiple types
     - Binary methods: archive, direct, deb, snap, rpm
     - Container methods: pod-manifest, deployment, helm-chart, kustomize
     - Component model fields: `install_method`, `archive_format`, `helm_chart_url`, `manifest_url`

5. **Custom URLs**: Require HTTPS? Verify checksums?
   - **Answer**: Support custom URLs, security to be implemented in download hooks
   - **Implementation**: `custom_binary_url`, `custom_image_url` fields in Component model
   - **TODO**: Add HTTPS validation and checksum verification in download hooks
5. **Priority Range**: Use 0-100 or allow negative? (Suggest: 0-100)

## Success Criteria

The implementation will be complete when:

1. ✅ All components use hook system
2. ✅ Downloads run in parallel
3. ✅ Dependencies properly sequenced
4. ✅ Custom binaries/images work
5. ✅ Existing manifests still work
6. ✅ Performance improvement measurable
7. ✅ Tests pass
8. ✅ Documentation complete

## References

- Original ChatGPT conversation: https://chatgpt.com/share/698f49ba-276c-8000-aa4b-275a1a42d996
- Documentation: `docs/component-lifecycle-hooks.md`
- Design: `docs/hook-system-design.md`
- Code: `src/kube_galaxy/pkg/components/__init__.py`

---

**Status**: Phase 1 Complete ✅  
**Next**: Begin Phase 2 - Component Migration  
**Updated**: 2026-02-13
