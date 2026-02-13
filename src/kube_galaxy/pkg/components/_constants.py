"""
Constants for component installation methods and configuration.

This module defines the supported installation methods for components
and provides timeout defaults for lifecycle stages.
"""

from enum import StrEnum


# Lifecycle stage enumeration
class HookStage(StrEnum):
    """Component lifecycle stages executed in order."""

    DOWNLOAD = "download"
    PRE_INSTALL = "pre_install"
    INSTALL = "install"
    CONFIGURE = "configure"
    BOOTSTRAP = "bootstrap"
    POST_BOOTSTRAP = "post_bootstrap"
    VERIFY = "verify"
    TEST = "test"


# Default timeout values (in seconds) for lifecycle stages
DEFAULT_DOWNLOAD_TIMEOUT = 300  # 5 minutes
DEFAULT_PRE_INSTALL_TIMEOUT = 60  # 1 minute
DEFAULT_INSTALL_TIMEOUT = 120  # 2 minutes
DEFAULT_CONFIGURE_TIMEOUT = 60  # 1 minute
DEFAULT_BOOTSTRAP_TIMEOUT = 300  # 5 minutes (kubeadm init can be slow)
DEFAULT_POST_BOOTSTRAP_TIMEOUT = 60  # 1 minute
DEFAULT_VERIFY_TIMEOUT = 300  # 5 minutes (cluster health checks)
DEFAULT_TEST_TIMEOUT = 600  # 10 minutes (component tests)

# Connection pool size for parallel downloads
DOWNLOAD_POOL_SIZE = 5  # Maximum concurrent downloads

# Error handling strategy
FAIL_FAST = True  # Fail immediately on first error (no retries)
