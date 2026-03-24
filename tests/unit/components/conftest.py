"""Shared fixtures for component unit tests."""

import platform
from dataclasses import dataclass, field

import pytest

from kube_galaxy.pkg.arch.detector import ArchInfo, get_arch_info
from kube_galaxy.pkg.cluster_context import ClusterContext
from kube_galaxy.pkg.units._base import RunResult, Unit


@dataclass
class MockUnit(Unit):
    """Test double for Unit — records run(), put() and download() calls."""

    _name: str = "mock"
    _run_results: list[RunResult] = field(default_factory=list)
    run_calls: list[tuple[list[str], dict]] = field(default_factory=list)
    put_calls: list[tuple[object, str]] = field(default_factory=list)
    download_calls: list[tuple[str, str]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self._name

    @property
    def arch(self) -> ArchInfo:
        return get_arch_info(platform.machine())

    def run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        privileged: bool = False,
        timeout: float | None = None,
    ) -> RunResult:
        self.run_calls.append(
            (list(cmd), {"check": check, "env": env, "privileged": privileged, "timeout": timeout})
        )
        if self._run_results:
            return self._run_results.pop(0)
        return RunResult(0, "", "")

    def set_run_results(self, *results: RunResult) -> None:
        """Queue results to return from successive run() calls."""
        self._run_results = list(results)

    def put(self, local, remote):  # type: ignore[override]
        self.put_calls.append((local, remote))

    def get(self, remote, local):  # type: ignore[override]
        pass

    def download(self, url, dest):  # type: ignore[override]
        self.download_calls.append((url, dest))

    def extract(self, archive, dest):  # type: ignore[override]
        pass

    def extract_zip(self, zip_file, path_in_zip, dest):  # type: ignore[override]
        pass

    def sha256(self, path):  # type: ignore[override]
        return "abc123"

    def wait_until_ready(self, timeout: float | None = None) -> None:  # type: ignore[override]
        pass


@pytest.fixture
def mock_unit() -> MockUnit:
    """Return a fresh MockUnit test double."""
    return MockUnit()


@pytest.fixture
def cluster_context() -> ClusterContext:
    """Return a fresh empty ClusterContext for component tests."""
    return ClusterContext()
