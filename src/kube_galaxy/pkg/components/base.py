"""
Base class for component installation and lifecycle management.

All component implementations should inherit from ComponentBase and
override the lifecycle hooks they need.
"""

from abc import ABC
from typing import Optional

from kube_galaxy.pkg.components.constants import (
    DEFAULT_BOOTSTRAP_TIMEOUT,
    DEFAULT_CONFIGURE_TIMEOUT,
    DEFAULT_DOWNLOAD_TIMEOUT,
    DEFAULT_INSTALL_TIMEOUT,
    DEFAULT_POST_BOOTSTRAP_TIMEOUT,
    DEFAULT_PRE_INSTALL_TIMEOUT,
)


class ComponentBase(ABC):
    """
    Base class for Kubernetes component installation.
    
    Each component should subclass this and override the lifecycle hooks
    it needs. The component has access to:
    - The full manifest (self.manifest)
    - Its own component configuration (self.component)
    - Architecture information (passed to hooks)
    
    Lifecycle hooks (all have default empty implementations):
    1. download_hook(repo, release, format, arch) - Download artifacts
    2. pre_install_hook() - Prepare machine for installation
    3. install_hook(repo, release, format, arch) - Install the component
    4. bootstrap_hook() - Initialize/start the component
    5. post_bootstrap_hook() - Post-initialization tasks
    6. configure_hook() - Final configuration and verification
    
    Each hook can be overridden. If not overridden, the default (empty)
    implementation is used and effectively skips that stage.
    
    Use regular instance attributes for state management between hooks.
    """
    
    # Timeout configuration (in seconds) - override in subclass
    DOWNLOAD_TIMEOUT = DEFAULT_DOWNLOAD_TIMEOUT
    PRE_INSTALL_TIMEOUT = DEFAULT_PRE_INSTALL_TIMEOUT
    INSTALL_TIMEOUT = DEFAULT_INSTALL_TIMEOUT
    BOOTSTRAP_TIMEOUT = DEFAULT_BOOTSTRAP_TIMEOUT
    POST_BOOTSTRAP_TIMEOUT = DEFAULT_POST_BOOTSTRAP_TIMEOUT
    CONFIGURE_TIMEOUT = DEFAULT_CONFIGURE_TIMEOUT
    
    # Component metadata - override in subclass
    COMPONENT_NAME: str = ""
    CATEGORY: str = ""
    DEPENDENCIES: list[str] = []
    PRIORITY: int = 50
    
    def __init__(self, manifest, component):
        """
        Initialize component with manifest context.
        
        Args:
            manifest: The full Manifest object
            component: The Component object for this specific component
        """
        self.manifest = manifest
        self.component = component
    
    # Properties for easy access to component configuration
    
    @property
    def custom_binary_url(self) -> Optional[str]:
        """Get custom binary URL from component config."""
        return self.component.custom_binary_url
    
    @property
    def custom_image_url(self) -> Optional[str]:
        """Get custom image URL from component config."""
        return self.component.custom_image_url
    
    @property
    def install_method(self) -> Optional[str]:
        """Get installation method from component config."""
        return self.component.install_method
    
    @property
    def archive_format(self) -> Optional[str]:
        """Get archive format from component config."""
        return self.component.archive_format
    
    @property
    def helm_chart_url(self) -> Optional[str]:
        """Get Helm chart URL from component config."""
        return self.component.helm_chart_url
    
    @property
    def helm_values(self) -> dict:
        """Get Helm values from component config."""
        return self.component.helm_values
    
    @property
    def manifest_url(self) -> Optional[str]:
        """Get manifest URL from component config."""
        return self.component.manifest_url
    
    @property
    def manifest_type(self) -> Optional[str]:
        """Get manifest type from component config."""
        return self.component.manifest_type
    
    @property
    def hook_config(self) -> dict:
        """Get hook-specific configuration from component config."""
        return self.component.hook_config
    
    # Lifecycle hooks - all have default empty implementations
    # Override in subclass as needed
    
    def download_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        """
        Download component artifacts.
        
        This hook runs in the DOWNLOAD stage (can be parallelized).
        Override to implement download logic.
        
        Args:
            repo: Repository URL
            release: Release tag/version
            format: Installation format (Binary, Container, Binary+Container)
            arch: Architecture (amd64, arm64, etc.)
        """
        pass
    
    def pre_install_hook(self) -> None:
        """
        Prepare machine for component installation.
        
        This hook runs in the PRE_INSTALL stage (sequential).
        Override to implement machine preparation (swapoff, sysctl, etc.).
        """
        pass
    
    def install_hook(self, repo: str, release: str, format: str, arch: str) -> None:
        """
        Install the component.
        
        This hook runs in the INSTALL stage (sequential, dependency-ordered).
        Override to implement installation logic.
        
        Args:
            repo: Repository URL
            release: Release tag/version
            format: Installation format (Binary, Container, Binary+Container)
            arch: Architecture (amd64, arm64, etc.)
        """
        pass
    
    def bootstrap_hook(self) -> None:
        """
        Initialize and start the component.
        
        This hook runs in the BOOTSTRAP stage (sequential, dependency-ordered).
        Override to implement service startup logic.
        """
        pass
    
    def post_bootstrap_hook(self) -> None:
        """
        Post-initialization tasks.
        
        This hook runs in the POST_BOOTSTRAP stage (sequential).
        Override to implement post-init configuration.
        """
        pass
    
    def configure_hook(self) -> None:
        """
        Final configuration and verification.
        
        This hook runs in the CONFIGURE stage (sequential).
        Override to implement verification logic.
        """
        pass
    
    # Legacy compatibility methods
    
    def install(self, repo: str, release: str, format: str, arch: str) -> None:
        """
        Legacy install method (combines download + install).
        
        For backward compatibility with existing code.
        """
        self.download_hook(repo, release, format, arch)
        self.install_hook(repo, release, format, arch)
    
    def configure(self) -> None:
        """
        Legacy configure method.
        
        For backward compatibility with existing code.
        """
        self.configure_hook()
