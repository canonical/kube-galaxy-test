from pathlib import Path

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
from kube_galaxy.pkg.utils.components import format_component_pattern


class ExampleComponent(ComponentBase):
    pass


def make_config(name: str = "example") -> ComponentConfig:
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="https://example/{{ repo.base-url }}/{{ release }}/{{ arch }}/binary",
        bin_path="./*",
        repo=RepoInfo(base_url="https://example.com/r"),
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
    """format_component_pattern resolves local:// base-url to a file:// URI rooted at cwd."""
    monkeypatch.chdir(tmp_path)
    repo = RepoInfo(base_url="local://")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/mybin-{{ arch }}",
        bin_path="./*",
        repo=repo,
    )
    config = ComponentConfig(
        name="mybin",
        category="test",
        release="1.0",
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info, repo)
    assert result == (tmp_path / f"mybin-{arch_info.k8s}").as_uri()


def test_format_component_pattern_subdir_and_ref(arch_info):
    """format_component_pattern handles {{ repo.subdir }} and {{ repo.ref }}."""
    repo = RepoInfo(base_url="https://github.com/org/repo", subdir="pkg/tool", ref="v2-branch")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/{{ repo.subdir }}/{{ repo.ref }}/{{ release }}",
        bin_path="./*",
        repo=repo,
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
    )
    config = ComponentConfig(
        name="sonobuoy",
        category="test",
        release="0.57.3",
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info, repo)
    assert result == (tmp_path / "components/sonobuoy").as_uri()


def test_format_component_pattern_prerender_name_in_subdir_remote(arch_info):
    """{{ name }} in repo.subdir is also expanded for remote (non-local) sources."""
    repo = RepoInfo(base_url="https://example.com", subdir="tools/{{ name }}")
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/{{ repo.subdir }}/release-{{ release }}",
        bin_path="./*",
        repo=repo,
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
        method=InstallMethod.NONE,
        source_format="",
        bin_path="./*",
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
    monkeypatch.setattr(SystemPaths, "tests_root", classmethod(lambda cls: tests_root))

    comp = ExampleComponent(
        {}, Manifest(name="m", description="d", kubernetes_version="1.0"), config, arch_info
    )
    comp.download_hook()

    dest = tests_root / "sonobuoy/spread/kube-galaxy"
    assert dest.exists()
    assert (dest / "task.yaml").read_text() == "summary: A fake task"


def test_ensure_temp_dir_calls_mkdir(monkeypatch, arch_info, tmp_path):
    comp = ExampleComponent(
        {}, Manifest(name="m", description="d", kubernetes_version="1.0"), make_config(), arch_info
    )
    # redirect component temp dir to test tmp_path to avoid /opt writes
    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, name: Path(tmp_path) / name / "temp"),
    )

    p = comp.component_tmp_dir
    # ensure_temp_dir should create the temp dir under tmp_path
    ret = comp.ensure_temp_dir()
    assert str(ret) == str(p)
    assert ret.exists()


def test_install_downloaded_binary_uses_install_binary(monkeypatch, tmp_path, arch_info):
    cfg = make_config("tool")
    comp = ExampleComponent(
        {}, Manifest(name="m", description="d", kubernetes_version="1.0"), cfg, arch_info
    )

    # create a fake binary file
    bin_path = tmp_path / "tool"
    bin_path.write_text("binary")

    def fake_install(binary_path, name, compname):
        return f"/usr/local/bin/{name}"

    monkeypatch.setattr("kube_galaxy.pkg.components._base.install_binary", fake_install)

    install_path = comp.install_downloaded_binary(bin_path, "tool")
    assert install_path == "/usr/local/bin/tool"


def test_create_systemd_service_and_write_config(monkeypatch, tmp_path, arch_info):
    comp = ExampleComponent(
        {}, Manifest(name="m", description="d", kubernetes_version="1.0"), make_config(), arch_info
    )
    recorded = []

    def fake_run(cmd, **kwargs):
        recorded.append(list(cmd))

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    # redirect component temp dir to test tmp_path to avoid /opt writes
    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, name: Path(tmp_path) / name / "temp"),
    )

    service_name = "svc"
    content = "[Unit]\nDescription=svc"
    comp.create_systemd_service(service_name, content, system_location=False)
    # Expect copy calls recorded (we use sudo cp now)
    assert any("cp" in cmd for cmd in recorded)

    # test write_config_file
    recorded.clear()
    comp.write_config_file("cfg", str(tmp_path / "cfgfile"))
    # Expect copy and chmod recorded for config write
    assert any("cp" in cmd for cmd in recorded)
    assert any("chmod" in cmd for cmd in recorded)


def test_remove_directories_and_files_and_remove_installed_binary(monkeypatch, tmp_path, arch_info):
    comp = ExampleComponent(
        {}, Manifest(name="m", description="d", kubernetes_version="1.0"), make_config(), arch_info
    )

    # create dirs and files
    d1 = tmp_path / "d1"
    d1.mkdir()
    f1 = tmp_path / "f1"
    f1.write_text("x")

    recorded = []

    def fake_run(cmd, **kwargs):
        recorded.append(list(cmd))

    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", fake_run)

    comp.remove_directories([str(d1)], "T")
    comp.remove_config_files([str(f1)], "T")

    assert any("rm" in cmd for cmd in recorded)

    # test remove_installed_binary actually deletes file
    b = tmp_path / "binfile"
    b.write_text("x")
    comp.install_path = str(b)
    comp.remove_installed_binary()
    assert not b.exists()
