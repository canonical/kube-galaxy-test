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
from kube_galaxy.pkg.utils.components import format_component_pattern


class ExampleComponent(ComponentBase):
    pass


def make_config(name: str = "example") -> ComponentConfig:
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="https://example/{{ repo.base-url }}/{{ release }}/{{ arch }}/binary",
        bin_path="./*",
    )
    repo = RepoInfo(base_url="https://example.com/r")
    return ComponentConfig(name=name, category="cat", release="v1", repo=repo, installation=install)


# ---------------------------------------------------------------------------
# Formatter unit tests (Mustache syntax: {{ variable }})
# ---------------------------------------------------------------------------


def test_format_component_pattern_hyphenated_key_native(arch_info):
    """Chevron natively resolves {{ repo.base-url }} via nested dict lookup.

    This is the key advantage over Jinja2: no preprocessing step is needed.
    Chevron splits on '.' and looks up 'base-url' in the repo dict, which
    Python happily stores as a hyphenated string key.
    """
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/path",
        bin_path="./*",
    )
    config = ComponentConfig(
        name="tool",
        category="test",
        release="1.0",
        repo=RepoInfo(base_url="https://example.com"),
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info)
    assert result == "https://example.com/path"


def test_format_component_pattern_remote(arch_info):
    """format_component_pattern supports {{ repo.base-url }} (hyphen) for remote sources."""
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/releases/download/v{{ release }}/bin-{{ arch }}",
        bin_path="./*",
    )
    config = ComponentConfig(
        name="mybin",
        category="test",
        release="1.2.3",
        repo=RepoInfo(base_url="https://github.com/org/mybin"),
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info)
    assert result == f"https://github.com/org/mybin/releases/download/v1.2.3/bin-{arch_info.k8s}"


def test_format_component_pattern_local_uses_cwd(arch_info, tmp_path, monkeypatch):
    """format_component_pattern resolves {{ repo.base-url }} to str(cwd) for local sources."""
    monkeypatch.chdir(tmp_path)
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/mybin-{{ arch }}",
        bin_path="./*",
    )
    config = ComponentConfig(
        name="mybin",
        category="test",
        release="1.0",
        repo=RepoInfo(base_url="local"),
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info)
    assert result == f"{tmp_path}/mybin-{arch_info.k8s}"


def test_format_component_pattern_subdir_and_ref(arch_info):
    """format_component_pattern handles {{ repo.subdir }} and {{ repo.ref }}."""
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/{{ repo.subdir }}/{{ repo.ref }}/{{ release }}",
        bin_path="./*",
    )
    config = ComponentConfig(
        name="tool",
        category="test",
        release="2.0",
        repo=RepoInfo(base_url="https://github.com/org/repo", subdir="pkg/tool", ref="v2-branch"),
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info)
    assert result == "https://github.com/org/repo/pkg/tool/v2-branch/2.0"


def test_format_component_pattern_empty_subdir_and_ref(arch_info):
    """Empty subdir and ref default to empty strings.

    Double slashes in the resulting URL are expected when optional fields are
    absent.  Callers should use full URLs directly in source-format when
    repo.subdir/repo.ref are not applicable.
    """
    install = InstallConfig(
        method=InstallMethod.BINARY,
        source_format="{{ repo.base-url }}/{{ repo.subdir }}/{{ repo.ref }}",
        bin_path="./*",
    )
    config = ComponentConfig(
        name="tool",
        category="test",
        release="1.0",
        repo=RepoInfo(base_url="https://github.com/org/repo"),
        installation=install,
    )
    result = format_component_pattern(install.source_format, config, arch_info)
    assert result == "https://github.com/org/repo//"


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

    p = Path(comp.component_tmp_dir)
    # ensure_temp_dir should create the temp dir under tmp_path
    ret = comp.ensure_temp_dir()
    assert str(ret) == str(p)
    assert ret.exists()


def test_download_binary_from_config_calls_download_file(monkeypatch, tmp_path, arch_info):
    cfg = make_config("mybin")
    comp = ExampleComponent(
        {}, Manifest(name="m", description="d", kubernetes_version="1.0"), cfg, arch_info
    )

    calls = []

    def fake_download(url, path):
        calls.append((url, str(path)))
        # ensure parent exists then create the file to simulate download
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("x")

    monkeypatch.setattr("kube_galaxy.pkg.components._base.download_file", fake_download)
    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", lambda *a, **k: None)
    # redirect component temp dir to test tmp_path to avoid /opt writes
    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, name: Path(tmp_path) / name / "temp"),
    )

    p = comp.download_filename_from_config()
    assert calls, "download_file was not called"
    assert p.exists()


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
    assert comp.install_path == install_path


def test_download_and_extract_archive_calls_extract(monkeypatch, tmp_path, arch_info):
    cfg = make_config("foo")
    cfg.installation = InstallConfig(
        method=InstallMethod.BINARY_ARCHIVE,
        source_format="https://example/{{ repo.base-url }}/{{ release }}/{{ arch }}/archive.tar.gz",
        bin_path="./*",
    )
    comp = ExampleComponent(
        {}, Manifest(name="m", description="d", kubernetes_version="1.0"), cfg, arch_info
    )

    events = []

    def fake_download(url, path):
        # ensure parent exists then create a fake archive file
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("archive")
        events.append(("download", url, str(path)))

    def fake_extract(archive_path, dest):
        events.append(("extract", str(archive_path), str(dest)))
        dest.mkdir(exist_ok=True)
        # create a fake binary inside
        (dest / "foo").write_text("x")

    monkeypatch.setattr("kube_galaxy.pkg.components._base.download_file", fake_download)
    monkeypatch.setattr("kube_galaxy.pkg.components._base.extract_archive", fake_extract)
    monkeypatch.setattr("kube_galaxy.pkg.components._base.run", lambda *a, **k: None)
    # redirect component temp dir to test tmp_path to avoid /opt writes
    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, name: Path(tmp_path) / name / "temp"),
    )

    dest = comp.download_and_extract_archive("amd64")
    assert any(e[0] == "extract" for e in events)
    assert (dest / "foo").exists()


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
