"""
Sonobuoy component installation and management.

The Sonobuoy tool is used for Kubernetes conformance testing.
The test suite definition lives locally in the repository at
``components/sonobuoy/`` and is copied to the shared tests root
during the install stage so that spread can discover and run it.
"""

import shutil
from pathlib import Path

from kube_galaxy.pkg.components import ComponentBase, register_component
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.utils.logging import info


@register_component("sonobuoy")
class Sonobuoy(ComponentBase):
    """
    Sonobuoy component for Kubernetes conformance testing.

    The component source is local (``base-url: local`` in the manifest).
    The install hook copies the pre-existing spread task definition from
    ``components/sonobuoy/`` (relative to the working directory) into
    ``SystemPaths.tests_root() / "sonobuoy"``, making it available to the
    spread test orchestrator.
    """

    def install_hook(self) -> None:
        """Copy the local sonobuoy spread suite to the shared tests root."""
        local_suite = Path.cwd() / "components" / self.name
        dest = self.suite_root

        if dest.exists():
            shutil.rmtree(dest)

        shutil.copytree(local_suite, dest)
        info(f"Copied sonobuoy test suite from {local_suite} to {dest}")

    def remove_hook(self) -> None:
        """Remove the copied sonobuoy suite from the shared tests root."""
        shutil.rmtree(self.suite_root, ignore_errors=True)

    @property
    def suite_root(self) -> Path:
        """Root of the sonobuoy test suite inside the shared tests directory."""
        return SystemPaths.tests_root() / self.name

    @property
    def suite_path(self) -> Path:
        """Path to the spread/kube-galaxy task directory inside the tests root."""
        return self.suite_root / "spread/kube-galaxy"

    @property
    def task_path(self) -> Path:
        """Path to the task.yaml inside the tests root."""
        return self.suite_path / "task.yaml"
