"""
Base class for component installation and lifecycle management.

All component implementations should inherit from ComponentBase and
override the lifecycle hooks they need.
"""

from typing import ClassVar

from kube_galaxy.pkg.components._constants import (
    DEFAULT_BOOTSTRAP_TIMEOUT,
    DEFAULT_CONFIGURE_TIMEOUT,
    DEFAULT_DOWNLOAD_TIMEOUT,
    DEFAULT_INSTALL_TIMEOUT,
    DEFAULT_POST_BOOTSTRAP_TIMEOUT,
    DEFAULT_PRE_INSTALL_TIMEOUT,
    DEFAULT_TEST_TIMEOUT,
    DEFAULT_VERIFY_TIMEOUT,
)
from kube_galaxy.pkg.manifest.models import ComponentConfig, Manifest
from kube_galaxy.pkg.utils.errors import ComponentError


class ComponentBase:
    """
    Base class for Kubernetes component installation.

    Each component should subclass this and override the lifecycle hooks
    it needs. The component has access to:
    - The full manifest (self.manifest)
    - Its own component configuration (self.config)
    - Architecture information (passed to hooks)

    Lifecycle hooks (all have default empty implementations):
    1. download_hook(repo, release, method, source_format, arch) - Download artifacts
    2. pre_install_hook() - Prepare machine for installation
    3. install_hook(repo, release, method, source_format, arch) - Install the component
    4. configure_hook() - Configure component (config files, settings)
    5. bootstrap_hook() - Initialize/start the component
    6. post_bootstrap_hook() - Post-initialization tasks
    7. verify_hook() - Verify component is working
    8. test_hook() - Run component tests (optional)

    Each hook can be overridden. If not overridden, the default (empty)
    implementation is used and effectively skips that stage.

    Use regular instance attributes for state management between hooks.
    """

    # Timeout configuration (in seconds) - override in subclass
    DOWNLOAD_TIMEOUT = DEFAULT_DOWNLOAD_TIMEOUT
    PRE_INSTALL_TIMEOUT = DEFAULT_PRE_INSTALL_TIMEOUT
    INSTALL_TIMEOUT = DEFAULT_INSTALL_TIMEOUT
    CONFIGURE_TIMEOUT = DEFAULT_CONFIGURE_TIMEOUT
    BOOTSTRAP_TIMEOUT = DEFAULT_BOOTSTRAP_TIMEOUT
    POST_BOOTSTRAP_TIMEOUT = DEFAULT_POST_BOOTSTRAP_TIMEOUT
    VERIFY_TIMEOUT = DEFAULT_VERIFY_TIMEOUT
    TEST_TIMEOUT = DEFAULT_TEST_TIMEOUT

    # Component metadata - override in subclass
    COMPONENT_NAME: str = ""
    CATEGORY: str = ""
    DEPENDENCIES: ClassVar[list[str]] = []
    PRIORITY: int = 50

    def __init__(
        self,
        instances: dict[str, "ComponentBase"],
        manifest: Manifest,
        config: ComponentConfig,
    ) -> None:
        """
        Initialize component with instances, manifest, and config.

        Args:
            instances: Dict of all component instances (growing as components are created)
            manifest: The full Manifest object
            config: The ComponentConfig object for this specific component
        """
        self.instances = instances
        self.manifest = manifest
        self.config = config
        self.install_path: str | None = None

    def _install_path(self, component: str) -> str:
        """
        Get binary path from specified component.

        Returns:
            Binary path of the specified component
        """
        if component_instance := self.instances.get(component):
            if component_instance.install_path:
                return component_instance.install_path

        raise ComponentError(f"Install path for component '{component}' not found")

    # Lifecycle hooks - all have default empty implementations
    # Override in subclass as needed

    def download_hook(self, arch: str) -> None:
        """
        Download component artifacts.

        This hook runs in the DOWNLOAD stage (can be parallelized).
        Override to implement download logic.

        Access component config via self.config (repo, release, installation).

        Args:
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

    def install_hook(self, arch: str) -> None:
        """
        Install the component.

        This hook runs in the INSTALL stage (sequential,
        dependency-ordered). Override to implement installation logic.

        Access component config via self.config (repo, release, installation).

        Args:
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
        Configure the component (create config files, etc.).

        This hook runs in the CONFIGURE stage before BOOTSTRAP (sequential).
        Override to implement configuration logic.
        """
        pass

    def verify_hook(self) -> None:
        """
        Verify the component is working correctly.

        This hook runs in the VERIFY stage (sequential).
        Override to implement health check logic.
        """
        pass

    def test_hook(self) -> None:
        """
        Run tests on the component.

        This hook runs in the TEST stage (sequential).
        Override to implement testing logic (e.g., spread tests).
        """
        pass

    def remove_hook(self) -> None:
        """
        Remove/uninstall the component.

        This hook runs during component removal.
        Override to implement cleanup logic.
        """
        pass
