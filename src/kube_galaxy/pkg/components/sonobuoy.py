"""
Sonobuoy component installation and management.

The Sonobuoy tool is used for Kubernetes conformance testing.
"""

import shutil
from pathlib import Path

from kube_galaxy.pkg.components import ComponentBase, register_component
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.utils.components import (
    format_component_pattern,
)
from kube_galaxy.pkg.utils.logging import info

TASK = """
summary: Sonobuoy CNCF execution
execute: |
    wget  {url} -O sonobuoy.tar.gz
    tar -xvf sonobuoy.tar.gz
    ./sonobuoy delete --kubeconfig=$KUBECONFIG
    ./sonobuoy run --kubeconfig=$KUBECONFIG --mode=quick --wait=$TEST_TIMEOUT_M
"""


@register_component("sonobuoy")
class Sonobuoy(ComponentBase):
    """
    Sonobuoy component for Kubernetes infrastructure.

    This component handles the Sonobuoy deployment.
    """

    def download_hook(self) -> None:
        """Prepare Sonobuoy test suite definition."""
        self.task_path.parent.mkdir(parents=True, exist_ok=True)

    def install_hook(self) -> None:
        """Run Sonobuoy conformance tests."""
        url = format_component_pattern(
            self.config.installation.source_format, self.config, self.arch_info
        )
        info(f"Preparing Sonobuoy test suite with binary from {url}")
        self.task_path.write_text(TASK.format(url=url))

    def remove_hook(self) -> None:
        shutil.rmtree(self.suite_path, ignore_errors=True)

    @property
    def suite_path(self) -> Path:
        """Path to the Sonobuoy test suite definition."""
        return SystemPaths.tests_root() / self.name / "spread/kube-galaxy"

    @property
    def task_path(self) -> Path:
        """Path to the Sonobuoy task definition."""
        return self.suite_path / "task.yaml"
