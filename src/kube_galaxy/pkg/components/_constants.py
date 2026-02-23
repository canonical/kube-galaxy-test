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
    VERIFY = "verify"


# Connection pool size for parallel downloads
DOWNLOAD_POOL_SIZE = 5  # Maximum concurrent downloads

# Error handling strategy
FAIL_FAST = True  # Fail immediately on first error (no retries)
