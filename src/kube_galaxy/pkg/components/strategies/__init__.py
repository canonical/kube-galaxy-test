"""Strategy lookup tables for install and test methods.

Each entry maps an InstallMethod/TestMethod enum value to a singleton strategy
object.  To add support for a new method, create a new module in this package,
implement the strategy class, and add a single entry here.
"""

from kube_galaxy.pkg.manifest.models import InstallMethod, TestMethod

from ._base import _InstallStrategy, _TestStrategy
from .binary import _BinaryInstallStrategy
from .binary_archive import _BinaryArchiveInstallStrategy
from .container_image import _ContainerImageInstallStrategy
from .container_image_archive import _ContainerImageArchiveInstallStrategy
from .container_manifest import _ContainerManifestInstallStrategy
from .spread import _SpreadTestStrategy

_INSTALL_STRATEGIES: dict[InstallMethod, _InstallStrategy] = {
    InstallMethod.BINARY: _BinaryInstallStrategy,
    InstallMethod.BINARY_ARCHIVE: _BinaryArchiveInstallStrategy,
    InstallMethod.CONTAINER_IMAGE_ARCHIVE: _ContainerImageArchiveInstallStrategy,
    InstallMethod.CONTAINER_IMAGE: _ContainerImageInstallStrategy,
    InstallMethod.CONTAINER_MANIFEST: _ContainerManifestInstallStrategy,
    InstallMethod.NONE: _InstallStrategy(),
}

_TEST_STRATEGIES: dict[TestMethod, _TestStrategy] = {
    TestMethod.SPREAD: _SpreadTestStrategy,
    TestMethod.NONE: _TestStrategy(),
}

__all__ = [
    "_INSTALL_STRATEGIES",
    "_TEST_STRATEGIES",
    "_InstallStrategy",
    "_TestStrategy",
]
