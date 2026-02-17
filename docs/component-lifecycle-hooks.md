# Component Lifecycle Hook System

## Overview

The component lifecycle hook system provides a structured way to manage Kubernetes component installation with support for:
- Parallel downloads with connection pooling
- Dependency-based execution ordering
- Custom binary and image URLs
- Extensible lifecycle stages

## Hook Stages

Components can implement any or all of these lifecycle hooks:

### 1. DOWNLOAD
**Purpose**: Download binaries and container images
**Execution**: Can run in parallel with connection pooling
**When**: Before any installation begins

### 2. PRE_INSTALL
**Purpose**: Prepare the machine for installation
**Execution**: Sequential, after all downloads complete
**When**: Before installing any components

### 3. INSTALL
**Purpose**: Install the component
**Execution**: Sequential, respecting dependencies
**When**: After downloads and pre-install hooks

### 4. BOOTSTRAP
**Purpose**: Initialize and start the component
**Execution**: Sequential, respecting dependencies
**When**: After all components are installed

### 5. POST_BOOTSTRAP
**Purpose**: Post-initialization configuration
**Execution**: Sequential, after bootstrap
**When**: After cluster/services are running

### 6. CONFIGURE
**Purpose**: Final configuration and verification
**Execution**: Sequential, after post_bootstrap
**When**: Final stage before completion

## Execution Flow

```
Stage 1: DOWNLOAD (parallel for all components)
  ├─ runc download
  ├─ containerd download
  ├─ kubelet download
  └─ kubeadm download

Stage 2: PRE_INSTALL (sequential, dependency-ordered)
  └─ (machine preparation, if any components define this)

Stage 3: INSTALL (sequential, dependency-ordered)
  ├─ runc install
  ├─ containerd install (after runc)
  ├─ kubelet install
  └─ kubeadm install (after containerd, kubelet)

Stage 4: BOOTSTRAP (sequential, dependency-ordered)
  ├─ containerd bootstrap (start service)
  └─ kubeadm bootstrap (kubeadm init)

Stage 5: POST_BOOTSTRAP (sequential)
  └─ kubeadm post_bootstrap (get kubeconfig)

Stage 6: CONFIGURE (sequential, dependency-ordered)
  ├─ containerd configure (verify)
  └─ kubeadm configure (verify)
```

## Component Registration

Components register using a class-based decorator pattern:

```python
from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.components import register_component_class

@register_component_class
class MyComponent(ComponentBase):
    """My component description."""

    CATEGORY = "category"
    DEPENDENCIES = ["dependency1"]
    PRIORITY = 25

    def download_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        # Download logic
        pass

    def install_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        # Install logic
        pass
```

The `@register_component_class` decorator registers the component at module import time, making it available to the execution engine.

## Best Practices

1. **Keep hooks idempotent**: Hooks should handle being called multiple times

2. **Use instance attributes for state**: Share data between hooks using `self.attribute_name`

3. **Use properties for configuration**: Access manifest config via `self.custom_binary_url`, `self.hook_config`, etc.

4. **Don't override hooks you don't need**: The base class provides empty defaults

5. **Set dependencies correctly**: List all components that must be installed before yours

6. **Use appropriate timeouts**: Override timeout constants for long-running operations

7. **Handle errors gracefully**: Raise clear exceptions if prerequisites aren't met
2. **Use module state**: Share data between hooks via module-level variables
3. **Fail fast**: Raise exceptions early if preconditions aren't met
4. **Log progress**: Use the logging utilities for user feedback
5. **Test dependencies**: Verify all dependencies are listed correctly
