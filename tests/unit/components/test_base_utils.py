from kube_galaxy.pkg.cluster_context import ClusterContext
from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.literals import SystemPaths
from kube_galaxy.pkg.manifest.models import (
    ComponentConfig,
    InstallConfig,
    InstallMethod,
    Manifest,
    RepoInfo,
)
from kube_galaxy.pkg.manifest.models import (
    TestConfig as ComponentTestConfig,
)
from kube_galaxy.pkg.manifest.models import (
    TestMethod as ComponentTestMethod,
)
from kube_galaxy.pkg.units._base import RunResult
from kube_galaxy.pkg.utils.components import format_component_pattern, install_from_archive
from tests.unit.components.conftest import MockUnit


class ExampleComponent(ComponentBase):
    pass


def make_config(name: str = "example") -> ComponentConfig:
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="https://example/{{ repo.base-url }}/{{ release }}/{{ arch }}/binary",
        bin_path="./*",
        repo=RepoInfo(base_url="https://example.com/r"),
        retag_format="",
    )
    return ComponentConfig(name=name, category="cat", release="v1", installation=install)


# ---------------------------------------------------------------------------
# Formatter unit tests (Mustache syntax: {{ variable }})
# ---------------------------------------------------------------------------


def test_format_component_pattern_hyphenated_key_native(arch_info):
    """Chevron natively resolves {{ repo.base-url }} via nested dict lookup.

    This is the key advantage over Jinja2: no preprocessing step is needed.
    Chevron splits on '.' and looks up 'base-url' in the repo dict, which
    Python happily stores as a hyphenated string key.
    """
    repo = RepoInfo(base_url="https://example.com")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/path",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    config = ComponentConfig(
        name="tool",
        category="test",
        release="1.0",
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info, repo)
    assert result == "https://example.com/path"


def test_format_component_pattern_remote(arch_info):
    """format_component_pattern supports {{ repo.base-url }} (hyphen) for remote sources."""
    repo = RepoInfo(base_url="https://github.com/org/mybin")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/releases/download/v{{ release }}/bin-{{ arch }}",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    config = ComponentConfig(
        name="mybin",
        category="test",
        release="1.2.3",
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info, repo)
    assert result == f"https://github.com/org/mybin/releases/download/v1.2.3/bin-{arch_info.k8s}"


def test_format_component_pattern_local_uses_cwd(arch_info, tmp_path, monkeypatch):
    """format_component_pattern preserves local:// base-url as-is; download_file resolves it."""
    monkeypatch.chdir(tmp_path)
    repo = RepoInfo(base_url="local://")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/mybin-{{ arch }}",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    config = ComponentConfig(
        name="mybin",
        category="test",
        release="1.0",
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info, repo)
    assert result == f"local:///mybin-{arch_info.k8s}"


def test_format_component_pattern_subdir_and_ref(arch_info):
    """format_component_pattern handles {{ repo.subdir }} and {{ repo.ref }}."""
    repo = RepoInfo(base_url="https://github.com/org/repo", subdir="pkg/tool", ref="v2-branch")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/{{ repo.subdir }}/{{ repo.ref }}/{{ release }}",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    config = ComponentConfig(
        name="tool",
        category="test",
        release="2.0",
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info, repo)
    assert result == "https://github.com/org/repo/pkg/tool/v2-branch/2.0"


def test_format_component_pattern_empty_subdir_and_ref(arch_info):
    """Empty subdir and ref default to empty strings.

    Double slashes in the resulting URL are expected when optional fields are
    absent.  Callers should use full URLs directly in source-format when
    repo.subdir/repo.ref are not applicable.
    """
    repo = RepoInfo(base_url="https://github.com/org/repo")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/{{ repo.subdir }}/{{ repo.ref }}",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    config = ComponentConfig(
        name="tool",
        category="test",
        release="1.0",
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info, repo)
    assert result == "https://github.com/org/repo//"


def test_format_component_pattern_name_variable(arch_info):
    """format_component_pattern supports {{ name }} as the component name."""
    repo = RepoInfo(base_url="https://example.com")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/components/{{ name }}/bin",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    config = ComponentConfig(
        name="mytool",
        category="test",
        release="1.0",
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info, repo)
    assert result == "https://example.com/components/mytool/bin"


def test_format_component_pattern_prerender_name_in_subdir(arch_info, tmp_path, monkeypatch):
    """{{ name }} in repo.subdir is expanded before the subdir is used in the template."""
    monkeypatch.chdir(tmp_path)
    repo = RepoInfo(base_url="local://", subdir="components/{{ name }}")
    install = InstallConfig(
        method=InstallMethod.NONE,
        source_format="{{ repo.base-url }}/{{ repo.subdir }}",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    config = ComponentConfig(
        name="sonobuoy",
        category="test",
        release="0.57.3",
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info, repo)
    assert result == "local:///components/sonobuoy"


def test_format_component_pattern_prerender_name_in_subdir_remote(arch_info):
    """{{ name }} in repo.subdir is also expanded for remote (non-local) sources."""
    repo = RepoInfo(base_url="https://example.com", subdir="tools/{{ name }}")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/{{ repo.subdir }}/release-{{ release }}",
        bin_path="./*",
        repo=repo,
        retag_format="",
    )
    config = ComponentConfig(
        name="mytool",
        category="test",
        release="3.0",
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info, repo)
    assert result == "https://example.com/tools/mytool/release-3.0"


def test_local_download_file_uses_source_format(monkeypatch, tmp_path, arch_info) -> None:
    """local:/// based download_file copies from the path resolved by test.source-format."""
    monkeypatch.chdir(tmp_path)

    # Create the local test suite at the path that source-format will resolve to
    suite_src = tmp_path / "components/sonobuoy/spread/kube-galaxy"
    suite_src.mkdir(parents=True)
    (suite_src / "task.yaml").write_text("summary: A fake task")

    install = InstallConfig(
        method=InstallMethod.NONE, source_format="", bin_path="./*", retag_format=""
    )
    test_cfg = ComponentTestConfig(
        method=ComponentTestMethod.SPREAD,
        source_format="{{ repo.base-url }}/components/{{ name }}/spread/kube-galaxy/task.yaml",
        repo=RepoInfo(base_url="local://"),
    )
    config = ComponentConfig(
        name="sonobuoy",
        category="test",
        release="0.57.3",
        installation=install,
        test=test_cfg,
    )

    tests_root = tmp_path / "tests_root"
    tests_root.mkdir()
    monkeypatch.setattr(SystemPaths, "local_tests_root", classmethod(lambda cls: tests_root))

    comp = ExampleComponent(
        ClusterContext(),
        Manifest(name="m", description="d", kubernetes_version="1.0"),
        config,
        arch_info,
    )
    comp.download_hook()

    dest = tests_root / "sonobuoy/spread/kube-galaxy"
    assert dest.exists()
    assert (dest / "task.yaml").read_text() == "summary: A fake task"


def test_ensure_temp_dir_creates_local_dir_only(monkeypatch, arch_info, tmp_path):
    mock_unit = MockUnit()
    comp = ExampleComponent(
        ClusterContext(),
        Manifest(name="m", description="d", kubernetes_version="1.0"),
        make_config(),
        arch_info,
    )
    comp.unit = mock_unit
    # Redirect staging root to tmp_path so no writes outside the test sandbox
    monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))

    # component_tmp_dir = staging_root / "opt/kube-galaxy/<name>/temp"
    p = comp.component_tmp_dir
    ret = comp.ensure_temp_dir()
    assert ret == p
    assert ret.exists()

    # ensure_temp_dir must NOT call unit.run — the unit may not be ready yet
    # (e.g. LXD VM agent not started) when this is called during DOWNLOAD hook
    assert not mock_unit.run_calls, (
        "ensure_temp_dir must not contact the unit — unit may not be ready at download time"
    )


def test_install_downloaded_binary_uses_install_binary(monkeypatch, tmp_path, arch_info):
    cfg = make_config("tool")
    comp = ExampleComponent(
        ClusterContext(),
        Manifest(name="m", description="d", kubernetes_version="1.0"),
        cfg,
        arch_info,
    )

    # create a fake binary file
    bin_path = tmp_path / "tool"
    bin_path.write_text("binary")

    def fake_install(binary_path, name, compname, unit):
        return f"/usr/local/bin/{name}"

    monkeypatch.setattr("kube_galaxy.pkg.components._base.install_binary", fake_install)

    install_path = comp.install_downloaded_binary(bin_path, "tool")
    assert install_path == "/usr/local/bin/tool"


def test_create_systemd_service_and_write_config(arch_info, monkeypatch, tmp_path):
    mock_unit = MockUnit()
    comp = ExampleComponent(
        ClusterContext(),
        Manifest(name="m", description="d", kubernetes_version="1.0"),
        make_config(),
        arch_info,
    )
    comp.unit = mock_unit

    # Redirect staging root to tmp_path so no writes outside the test sandbox
    monkeypatch.setattr(SystemPaths, "staging_root", classmethod(lambda cls: tmp_path))

    service_name = "svc"
    content = "[Unit]\nDescription=svc"
    comp.create_systemd_service(service_name, content, system_location=False)
    # File is pushed via unit.put(), not via unit.run(cp ...)
    assert any(service_name in str(dest) for _, dest in mock_unit.put_calls), (
        "expected unit.put() call for the service file"
    )
    recorded_cmds = [c[0] for c in mock_unit.run_calls]
    assert not any("cp" in cmd for cmd in recorded_cmds), "expected no cp commands on unit"
    assert any("systemctl" in cmd for cmd in recorded_cmds)

    # test write_config_file
    mock_unit.run_calls.clear()
    mock_unit.put_calls.clear()
    comp.write_config_file("cfg", str(tmp_path / "cfgfile"))
    assert mock_unit.put_calls, "expected unit.put() call for the config file"
    recorded_cmds = [c[0] for c in mock_unit.run_calls]
    assert any("chmod" in cmd for cmd in recorded_cmds)


def test_remove_directories_and_files_and_remove_installed_binary(arch_info, tmp_path):
    mock_unit = MockUnit()
    comp = ExampleComponent(
        ClusterContext(),
        Manifest(name="m", description="d", kubernetes_version="1.0"),
        make_config(),
        arch_info,
    )
    comp.unit = mock_unit

    # create dirs and files
    d1 = tmp_path / "d1"
    d1.mkdir()
    f1 = tmp_path / "f1"
    f1.write_text("x")

    comp.remove_directories([str(d1)], "T")
    comp.remove_config_files([str(f1)], "T")

    recorded_cmds = [c[0] for c in mock_unit.run_calls]
    assert any("rm" in cmd for cmd in recorded_cmds)

    # test remove_installed_binary: should call unit.run(rm -f ...) not local unlink
    mock_unit.run_calls.clear()
    comp.install_path = "/usr/local/bin/example"
    comp.remove_installed_binary()
    assert any(
        "rm" in cmd and "-f" in cmd and "/usr/local/bin/example" in cmd
        for cmd in [c[0] for c in mock_unit.run_calls]
    ), "expected unit.run(rm -f ...) for remove_installed_binary"


# ---------------------------------------------------------------------------
# install_from_archive unit tests
# ---------------------------------------------------------------------------


def test_install_from_archive_transfers_extracts_and_installs(tmp_path):
    """install_from_archive transfers archive to node, extracts it, and installs binaries."""
    mock_unit = MockUnit()

    archive = tmp_path / "archive.tar.gz"
    archive.write_bytes(b"fake-archive")

    node_extracted = "/opt/kube-galaxy/mycomp/temp/extracted"
    mock_unit.set_run_results(
        RunResult(0, "", ""),  # mkdir -p node_bin_dir
        RunResult(0, f"{node_extracted}/mycomp\n", ""),  # sh for-loop listing
    )

    result = install_from_archive(archive, "*", "mycomp", mock_unit)

    # Archive was transferred and extracted on the node
    assert len(mock_unit.download_calls) == 1
    assert mock_unit.download_calls[0][1] == "/opt/kube-galaxy/mycomp/temp/archive.tar.gz"

    # Binary was moved, chmod'd, and registered via update-alternatives
    all_run_cmds = [call[0] for call in mock_unit.run_calls]
    assert any(cmd[0] == "mv" for cmd in all_run_cmds)
    assert any(cmd[0] == "chmod" and "755" in cmd for cmd in all_run_cmds)
    assert any(cmd[0] == "update-alternatives" for cmd in all_run_cmds)

    # Return value maps binary name to its alternative path
    assert result == {"mycomp": f"{SystemPaths.USR_LOCAL_BIN}/mycomp"}


def test_install_from_archive_returns_all_matching_binaries(tmp_path):
    """install_from_archive returns entries for every binary matched by bin_pattern."""
    mock_unit = MockUnit()

    archive = tmp_path / "archive.tar.gz"
    archive.write_bytes(b"fake-archive")

    node_extracted = "/opt/kube-galaxy/mytool/temp/extracted"
    mock_unit.set_run_results(
        RunResult(0, "", ""),  # mkdir -p
        RunResult(0, f"{node_extracted}/bin-a\n{node_extracted}/bin-b\n", ""),  # sh listing
    )

    result = install_from_archive(archive, "bin-*", "mytool", mock_unit)

    assert set(result.keys()) == {"bin-a", "bin-b"}
    assert result["bin-a"] == f"{SystemPaths.USR_LOCAL_BIN}/bin-a"
    assert result["bin-b"] == f"{SystemPaths.USR_LOCAL_BIN}/bin-b"


def test_install_from_archive_no_match_returns_empty(tmp_path):
    """install_from_archive returns an empty dict when no binaries match the pattern."""
    mock_unit = MockUnit()

    archive = tmp_path / "archive.tar.gz"
    archive.write_bytes(b"fake-archive")

    mock_unit.set_run_results(
        RunResult(0, "", ""),  # mkdir -p
        RunResult(0, "", ""),  # sh listing — no output
    )

    result = install_from_archive(archive, "nonexistent-*", "mytool", mock_unit)

    assert result == {}
