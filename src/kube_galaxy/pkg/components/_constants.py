"""
Constants for component installation methods and configuration.

This module defines the supported installation methods for components
and provides timeout defaults for lifecycle stages.
"""

from enum import StrEnum

from kube_galaxy.pkg.literals import Timeouts


# Lifecycle stage enumeration
class HookStage(StrEnum):
    """Component lifecycle stages executed in order."""

    DOWNLOAD = "download"
    PRE_INSTALL = "pre_install"
    INSTALL = "install"
    CONFIGURE = "configure"
    BOOTSTRAP = "bootstrap"
    VERIFY = "verify"


# Default timeout values (in seconds) for lifecycle stages
DEFAULT_DOWNLOAD_TIMEOUT = Timeouts.DOWNLOAD_TIMEOUT
DEFAULT_PRE_INSTALL_TIMEOUT = Timeouts.NETWORK_TIMEOUT
DEFAULT_INSTALL_TIMEOUT = Timeouts.INSTALL_TIMEOUT
DEFAULT_CONFIGURE_TIMEOUT = Timeouts.CONFIGURE_TIMEOUT
DEFAULT_BOOTSTRAP_TIMEOUT = Timeouts.BOOTSTRAP_TIMEOUT
DEFAULT_VERIFY_TIMEOUT = Timeouts.DRAIN_TIMEOUT
DEFAULT_TEST_TIMEOUT = Timeouts.BOOTSTRAP_TIMEOUT

# Connection pool size for parallel downloads
DOWNLOAD_POOL_SIZE = 5  # Maximum concurrent downloads

# Error handling strategy
FAIL_FAST = True  # Fail immediately on first error (no retries)
