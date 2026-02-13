# Class-Based Component Development Guide

## Overview

Components in kube-galaxy v2 use an object-oriented class-based interface. Each component inherits from `ComponentBase` and implements the lifecycle hooks it needs.

## Why Class-Based?

The class-based approach provides several advantages:

1. **Context Access**: Components have direct access to:
   - The full manifest (`self.manifest`)
   - Their component configuration (`self.component`)
   - Easy access via properties: `self.custom_binary_url`, `self.install_method`, etc.

2. **State Management**: Clean state using regular instance attributes:
   - `self.binary_path = path` in one hook
   - `path = self.binary_path` in another hook
   - Pythonic, simple, no special methods needed

3. **Configuration**: Easy access to manifest configuration via properties:
   - `self.hook_config` - dict of hook-specific configuration
   - `self.custom_binary_url` - custom binary URL (if provided)
   - `self.install_method` - installation method

4. **Automatic Hook Skipping**: Don't override a hook = it doesn't run
   - Base class provides empty default implementations
   - No need to check if hooks should be skipped

5. **Testability**: Components can be instantiated with mock manifests for unit testing

6. **Maintainability**: Clear interface, better organization, easier to understand

## Creating a Component

### Basic Structure

```python
from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.components import register_component_class

@register_component_class
class MyComponent(ComponentBase):
    """Component description."""
    
    # Required: Component metadata
    COMPONENT_NAME = "mycomponent"
    CATEGORY = "tools"
    DEPENDENCIES = ["dependency1", "dependency2"]
    PRIORITY = 25
    
    # Optional: Custom timeouts (seconds)
    DOWNLOAD_TIMEOUT = 300
    INSTALL_TIMEOUT = 120
    BOOTSTRAP_TIMEOUT = 180
    
    # Implement hooks you need
    def download_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        """Download component artifacts."""
        # Your download logic
        pass
    
    def install_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        """Install the component."""
        # Your install logic
        pass
```

### Available Hooks

All hooks are optional - implement only what you need:

1. **download_hook(repo, release, format, arch)** - Download artifacts (parallel)
2. **pre_install_hook()** - Prepare machine (sequential)
3. **install_hook(repo, release, format, arch)** - Install component (sequential)
4. **bootstrap_hook()** - Start services (sequential)
5. **post_bootstrap_hook()** - Post-init tasks (sequential)
6. **configure_hook()** - Verify and configure (sequential)

### Accessing Manifest Data

```python
def download_hook(self, repo, release, format, arch):
    # Access full manifest
    cluster_name = self.manifest.name
    k8s_version = self.manifest.kubernetes_version
    
    # Access your component config
    component_name = self.component.name
    
    # Use properties (not getters!)
    custom_url = self.custom_binary_url
    install_method = self.install_method
    archive_format = self.archive_format
    
    # Use custom URL if provided, otherwise construct default
    url = custom_url or f"{repo}/releases/download/{release}/binary.tar.gz"
```

### State Management

Share data between hooks using instance attributes:

```python
def download_hook(self, repo, release, format, arch):
    # Download and extract
    temp_dir = Path("/tmp/mycomponent")
    binary_path = temp_dir / "binary"
    download_file(url, binary_path)
    
    # Store for next hook (just use instance attribute!)
    self.binary_path = binary_path

def install_hook(self, repo, release, format, arch):
    # Retrieve from previous hook
    if not hasattr(self, 'binary_path'):
        raise RuntimeError("Binary not downloaded")
    
    # Install
    install_binary(self.binary_path, 'mycomponent')
```

### Hook Configuration

Access hook-specific configuration from manifest:

```python
def bootstrap_hook(self):
    # Get hook configuration from manifest (via property)
    config = self.hook_config.get('bootstrap', {})
    pod_cidr = config.get('pod_network_cidr', '10.244.0.0/16')
    service_cidr = config.get('service_cidr', '10.96.0.0/12')
    
    # Use configuration
    run(['kubeadm', 'init', f'--pod-network-cidr={pod_cidr}'])
```

**Note**: Hook skipping is automatic! If you don't override a hook method, it simply won't run (the base class provides an empty default implementation).

## Complete Example

```python
from pathlib import Path
from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.components import register_component_class
from kube_galaxy.pkg.utils.components import download_file, install_binary
from kube_galaxy.pkg.utils.shell import run

@register_component_class
class EtcdComponent(ComponentBase):
    """Etcd distributed key-value store."""
    
    COMPONENT_NAME = "etcd"
    CATEGORY = "database"
    DEPENDENCIES = []
    PRIORITY = 5  # Install very early
    
    # Custom timeouts
    DOWNLOAD_TIMEOUT = 240
    INSTALL_TIMEOUT = 60
    BOOTSTRAP_TIMEOUT = 120
    
    def download_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        """Download etcd binary."""
        # Check for custom URL (via property, not getter!)
        custom_url = self.custom_binary_url
        
        if custom_url:
            url = custom_url
        else:
            # Construct default URL
            if not release.startswith('v'):
                release = f'v{release}'
            filename = f"etcd-{release}-linux-{arch}.tar.gz"
            url = f"{repo}/releases/download/{release}/{filename}"
        
        # Download
        temp_dir = Path(f"/tmp/{self.COMPONENT_NAME}-install")
        temp_dir.mkdir(parents=True, exist_ok=True)
        archive_path = temp_dir / "etcd.tar.gz"
        
        download_file(url, archive_path)
        
        # Extract
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir(exist_ok=True)
        run(['tar', 'xzf', str(archive_path), '-C', str(extract_dir)])
        
        # Store for install (use instance attribute!)
        self.extract_dir = extract_dir
    
    def install_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        """Install etcd binary."""
        if not hasattr(self, 'extract_dir'):
            raise RuntimeError("Archive not extracted")
        
        # Find and install binary
        binary_path = next(self.extract_dir.rglob('etcd'))
        install_binary(binary_path, 'etcd')
    
    def configure_hook(self) -> None:
        """Configure etcd systemd service."""
        service = """[Unit]
Description=etcd
After=network.target

[Service]
Type=notify
ExecStart=/usr/local/bin/etcd
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""
        service_path = Path('/etc/systemd/system/etcd.service')
        service_path.write_text(service)
        
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'enable', 'etcd'])
    
    def bootstrap_hook(self) -> None:
        """Start etcd service."""
        run(['systemctl', 'start', 'etcd'])
```

## Testing Components

```python
from kube_galaxy.pkg.manifest.models import Component, Manifest, NodeConfig
from kube_galaxy.pkg.components import create_component_instance

# Create test manifest
component_config = Component(
    name='mycomponent',
    category='test',
    release='1.0.0',
    repo='https://example.com',
    format='Binary',
    custom_binary_url='https://custom.example.com/binary.tar.gz'
)

manifest = Manifest(
    name='test-cluster',
    description='Test',
    kubernetes_version='1.35.0',
    nodes=NodeConfig(),
    components=[component_config]
)

# Create component instance
instance = create_component_instance('mycomponent', manifest, component_config)

# Test hooks
instance.download_hook('https://example.com', '1.0.0', 'Binary', 'amd64')
assert hasattr(instance, 'binary_path')

instance.install_hook('https://example.com', '1.0.0', 'Binary', 'amd64')
```

## Best Practices

1. **Use Properties**: Access config via properties like `self.custom_binary_url`, `self.install_method`
2. **State Management**: Use instance attributes like `self.binary_path` instead of special methods
3. **Configuration**: Access via `self.hook_config` dictionary
4. **Don't Override Unnecessary Hooks**: If you don't need a hook, just don't implement it
5. **Error Handling**: Raise clear exceptions with helpful messages
6. **Documentation**: Document each hook's purpose and requirements
7. **Timeouts**: Set realistic timeouts based on operation duration

## See Also

- `ComponentBase` source: `src/kube_galaxy/pkg/components/base.py`
- Example components: `kubeadm_v2.py`, `containerd_v2.py`
- Hook system design: `docs/hook-system-design.md`
