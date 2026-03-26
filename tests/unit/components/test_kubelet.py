from kube_galaxy.pkg.cluster_context import ClusterContext
from kube_galaxy.pkg.components.kubelet import Kubelet
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    RepoInfo,
)
from kube_galaxy.pkg.units._base import RunResult
from tests.unit.components.conftest import MockUnit


class ExampleResp:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_kubelet_configure_calls_urlopen_and_tee(arch_info, monkeypatch, tmp_path):
    # Prepare minimal manifest/config
    manifest = Manifest(name="m", description="d", kubernetes_version="1.24")
    repo = RepoInfo(base_url="https://github.com/kubernetes/kubernetes")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="https://example/{{ repo.base-url }}/{{ release }}/{{ arch }}/kubelet",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    config = ComponentConfig(name="kubelet", category="k8s", release="v1", installation=install)

    mock_unit = MockUnit()
    # Queue results for: mkdir target_dir, daemon-reload (service write)
    # plus mkdir parent, chmod (config file write)
    for _ in range(10):
        mock_unit._run_results.append(RunResult(0, "", ""))

    comp = Kubelet(ClusterContext(), manifest, config, arch_info)
    comp.unit = mock_unit
    # set an install path so replace works
    comp.install_path = "/usr/local/bin/kubelet"

    # Fake urlopen to return service content containing /usr/bin/kubelet
    monkeypatch.setattr(
        "kube_galaxy.pkg.components.kubelet.urlopen",
        lambda url: ExampleResp(b"ExecStart=/usr/bin/kubelet\n"),
    )

    # redirect staging root to test tmp_path to avoid cwd writes
    monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))

    # Call configure hook
    comp.configure_hook()

    # Expect the service file to be pushed to the unit via put()
    assert mock_unit.put_calls, "expected unit.put() call for service file"
