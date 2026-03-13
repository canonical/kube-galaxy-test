"""Unit tests for pkg.components.strategies sub-package.

Covers: binary, binary_archive, container_image, container_image_archive,
        container_manifest (remaining branches), spread (remaining branches).
"""

import bz2
import gzip
import lzma
from pathlib import Path

import pytest

from kube_galaxy.pkg.arch.detector import get_arch_info
from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.components.strategies.binary_archive import _bin_path
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
from kube_galaxy.pkg.utils.errors import ClusterError, ComponentError

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_manifest() -> Manifest:
    return Manifest(name="test-cluster", description="Test", kubernetes_version="1.35.0")


def _make_component(
    method: InstallMethod,
    source_format: str,
    bin_path: str = "./*",
    base_url: str = "https://github.com/org/repo",
    name: str = "mycomp",
    release: str = "v1.0.0",
    monkeypatch=None,
    tmp_path: Path | None = None,
    arch_info=None,
) -> ComponentBase:
    repo = RepoInfo(base_url=base_url)
    install = InstallConfig(
        method=method,
        source_format=source_format,
        bin_path=bin_path,
        repo=repo,
    )
    config = ComponentConfig(name=name, category="test", release=release, installation=install)
    manifest = _make_manifest()

    if monkeypatch is not None and tmp_path is not None:
        monkeypatch.setattr(
            SystemPaths,
            "component_temp_dir",
            classmethod(lambda cls, n: Path(tmp_path) / n / "temp"),
        )

    ai = arch_info if arch_info is not None else get_arch_info()
    return ComponentBase({}, manifest, config, ai)


# ===========================================================================
# binary.py
# ===========================================================================


class TestBinaryDownload:
    def test_download_remote_url(self, monkeypatch, tmp_path, arch_info):
        """_download fetches a remote URL and sets binary_path."""
        comp = _make_component(
            InstallMethod.BINARY,
            "https://example.com/releases/v{{ release }}/bin-{{ arch }}",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list[tuple[str, Path]] = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append((url, dest))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"binary")

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.binary.download_file", fake_download
        )

        comp.download_hook()

        assert len(calls) == 1
        url, dest = calls[0]
        assert f"v{comp.config.release}" in url
        assert comp.binary_path == dest
        assert dest.exists()

    def test_download_local_source(self, monkeypatch, tmp_path, arch_info):
        """_download resolves local:// base-url to a file:// URI via download_file."""
        comp = _make_component(
            InstallMethod.BINARY,
            "{{ repo.base-url }}/bin-{{ arch }}",
            base_url="local://fixtures",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append((url, dest))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"binary")

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.binary.download_file", fake_download
        )

        comp.download_hook()

        assert len(calls) == 1
        url, _ = calls[0]
        assert url.startswith("file://")
        assert comp.binary_path is not None

    def test_download_gh_artifact(self, monkeypatch, tmp_path, arch_info):
        """_download passes gh-artifact:// URL unchanged to download_file."""
        comp = _make_component(
            InstallMethod.BINARY,
            "{{ repo.base-url }}/bin-{{ arch }}",
            base_url="gh-artifact://artifact-name",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append((url, dest))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"binary")

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.binary.download_file", fake_download
        )

        comp.download_hook()

        assert len(calls) == 1
        url, _ = calls[0]
        assert url.startswith("gh-artifact://")
        assert comp.binary_path is not None


class TestBinaryInstall:
    def test_install_raises_if_binary_not_downloaded(self, monkeypatch, tmp_path, arch_info):
        """_install raises ComponentError when binary_path is not set."""
        comp = _make_component(
            InstallMethod.BINARY,
            "https://example.com/bin",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        # Don't call download; binary_path remains None
        with pytest.raises(ComponentError, match="binary not downloaded"):
            comp.install_hook()

    def test_install_raises_if_binary_file_missing(self, monkeypatch, tmp_path, arch_info):
        """_install raises ComponentError when binary_path points to non-existent file."""
        comp = _make_component(
            InstallMethod.BINARY,
            "https://example.com/bin",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        comp.binary_path = tmp_path / "does-not-exist"
        with pytest.raises(ComponentError, match="binary not downloaded"):
            comp.install_hook()

    def test_install_calls_install_binary(self, monkeypatch, tmp_path, arch_info):
        """_install calls install_downloaded_binary and sets install_path."""
        comp = _make_component(
            InstallMethod.BINARY,
            "https://example.com/bin",
            name="mycomp",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        binary = tmp_path / "mycomp"
        binary.write_bytes(b"binary")
        comp.binary_path = binary

        monkeypatch.setattr(
            "kube_galaxy.pkg.components._base.install_binary",
            lambda path, name, comp_name: f"/usr/local/bin/{name}",
        )

        comp.install_hook()

        assert comp.install_path == "/usr/local/bin/mycomp"


# ===========================================================================
# binary_archive.py
# ===========================================================================


class TestBinaryArchiveBinPath:
    def test_bin_path_resolves_pattern(self, monkeypatch, tmp_path, arch_info):
        """_bin_path formats the bin_path template correctly."""
        comp = _make_component(
            InstallMethod.BINARY_ARCHIVE,
            "https://example.com/archive-{{ arch }}.tar.gz",
            bin_path="bin/mycomp-{{ arch }}",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        result = _bin_path(comp)
        assert arch_info.k8s in result


class TestBinaryArchiveDownload:
    def test_download_remote(self, monkeypatch, tmp_path, arch_info):
        """_download fetches archive from remote URL and extracts it."""
        comp = _make_component(
            InstallMethod.BINARY_ARCHIVE,
            "https://example.com/archive-{{ arch }}.tar.gz",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        download_calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            download_calls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake-archive")

        extract_calls: list = []

        def fake_extract(archive: Path, dest_dir: Path) -> None:
            extract_calls.append((archive, dest_dir))
            dest_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.binary_archive.download_file", fake_download
        )
        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.binary_archive.extract_archive", fake_extract
        )

        comp.download_hook()

        assert len(download_calls) == 1
        assert len(extract_calls) == 1

    def test_download_local(self, monkeypatch, tmp_path, arch_info):
        """_download resolves local:// base-url to a file:// URI via download_file."""
        comp = _make_component(
            InstallMethod.BINARY_ARCHIVE,
            "{{ repo.base-url }}/archive-{{ arch }}.tar.gz",
            base_url="local://fixtures",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake-archive")

        def fake_extract(archive: Path, dest_dir: Path) -> None:
            dest_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.binary_archive.download_file", fake_download
        )
        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.binary_archive.extract_archive", fake_extract
        )

        comp.download_hook()

        assert len(calls) == 1
        assert calls[0].startswith("file://")

    def test_download_gh_artifact(self, monkeypatch, tmp_path, arch_info):
        """_download passes gh-artifact:// URL unchanged to download_file."""
        comp = _make_component(
            InstallMethod.BINARY_ARCHIVE,
            "{{ repo.base-url }}/artifact-{{ arch }}.tar.gz",
            base_url="gh-artifact://artifact-name",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake-archive")

        def fake_extract(archive: Path, dest_dir: Path) -> None:
            dest_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.binary_archive.download_file", fake_download
        )
        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.binary_archive.extract_archive", fake_extract
        )

        comp.download_hook()

        assert len(calls) == 1
        assert calls[0].startswith("gh-artifact://")


class TestBinaryArchiveInstall:
    def test_install_raises_if_not_downloaded(self, monkeypatch, tmp_path, arch_info):
        """_install raises ComponentError when extracted_dir does not exist."""
        comp = _make_component(
            InstallMethod.BINARY_ARCHIVE,
            "https://example.com/archive.tar.gz",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        # extracted_dir is under component_tmp_dir/extracted; it doesn't exist yet
        with pytest.raises(ComponentError, match="archive not downloaded"):
            comp.install_hook()

    def test_install_installs_matching_binaries(self, monkeypatch, tmp_path, arch_info):
        """_install globs the extracted_dir and installs matching files."""
        comp = _make_component(
            InstallMethod.BINARY_ARCHIVE,
            "https://example.com/archive.tar.gz",
            bin_path="*",
            name="mycomp",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        # Create the extracted directory with a matching binary
        extracted = Path(comp.component_tmp_dir) / "extracted"
        extracted.mkdir(parents=True, exist_ok=True)
        binary = extracted / "mycomp"
        binary.write_bytes(b"binary")

        installed: list[str] = []

        def fake_install_binary(path: Path, name: str, comp_name: str) -> str:
            installed.append(name)
            return f"/usr/local/bin/{name}"

        monkeypatch.setattr(
            "kube_galaxy.pkg.components._base.install_binary",
            fake_install_binary,
        )

        comp.install_hook()

        assert "mycomp" in installed
        assert comp.install_path == "/usr/local/bin/mycomp"

    def test_install_sets_install_path_for_named_binary(self, monkeypatch, tmp_path, arch_info):
        """_install sets install_path only for the binary matching comp.name."""
        comp = _make_component(
            InstallMethod.BINARY_ARCHIVE,
            "https://example.com/archive.tar.gz",
            bin_path="*",
            name="mycomp",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        extracted = Path(comp.component_tmp_dir) / "extracted"
        extracted.mkdir(parents=True, exist_ok=True)
        # Create two binaries; only "mycomp" should set install_path
        (extracted / "mycomp").write_bytes(b"binary1")
        (extracted / "other").write_bytes(b"binary2")

        monkeypatch.setattr(
            "kube_galaxy.pkg.components._base.install_binary",
            lambda path, name, comp_name: f"/usr/local/bin/{name}",
        )

        comp.install_hook()

        assert comp.install_path == "/usr/local/bin/mycomp"


# ===========================================================================
# container_image.py
# ===========================================================================


class TestContainerImageDownload:
    def test_download_sets_repo_and_tag(self, monkeypatch, tmp_path, arch_info):
        """_download parses image:tag and stores in comp.image_repository/image_tag."""
        comp = _make_component(
            InstallMethod.CONTAINER_IMAGE,
            "registry.k8s.io/pause:{{ release }}",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
            release="3.9",
        )

        comp.download_hook()

        assert comp.image_repository == "registry.k8s.io/pause"
        assert comp.image_tag == "3.9"

    @pytest.mark.parametrize(
        "scheme_url",
        [
            "local://fixtures",
            "gh-artifact://artifact-name",
            "https://github.com/org/repo",
            "file:///some/local/path",
        ],
    )
    def test_download_raises_for_url_scheme(
        self, scheme_url: str, monkeypatch, tmp_path, arch_info
    ):
        """_download raises ComponentError for any base-url that contains a URL scheme."""
        comp = _make_component(
            InstallMethod.CONTAINER_IMAGE,
            "{{ repo.base-url }}/image:latest",
            base_url=scheme_url,
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        with pytest.raises(ComponentError, match="does not support URL schemes"):
            comp.download_hook()

    def test_download_raises_for_invalid_format(self, monkeypatch, tmp_path, arch_info):
        """_download raises ComponentError when image string has no colon."""
        comp = _make_component(
            InstallMethod.CONTAINER_IMAGE,
            "registry.k8s.io/pause-no-tag",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        with pytest.raises(ComponentError, match="Invalid container image format"):
            comp.download_hook()


# ===========================================================================
# container_image_archive.py
# ===========================================================================


def _make_cia_component(
    source_format: str,
    base_url: str = "https://example.com",
    monkeypatch=None,
    tmp_path: Path | None = None,
    arch_info=None,
) -> ComponentBase:
    return _make_component(
        InstallMethod.CONTAINER_IMAGE_ARCHIVE,
        source_format,
        base_url=base_url,
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        arch_info=arch_info,
    )


def _patch_cia_download(monkeypatch, content: bytes = b"data") -> list:
    calls: list = []

    def fake_download(url: str, dest: Path) -> None:
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

    monkeypatch.setattr(
        "kube_galaxy.pkg.components.strategies.container_image_archive.download_file",
        fake_download,
    )
    return calls


class TestContainerImageArchiveDownload:
    def test_download_plain_tar(self, monkeypatch, tmp_path, arch_info):
        """.tar files are renamed to image.tar."""
        comp = _make_cia_component(
            "https://example.com/image.tar",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        _patch_cia_download(monkeypatch, b"tar-content")

        comp.download_hook()

        image_tar = Path(comp.component_tmp_dir) / "extracted" / "image.tar"
        assert image_tar.exists()
        assert image_tar.read_bytes() == b"tar-content"

    def test_download_tar_gz(self, monkeypatch, tmp_path, arch_info):
        """.tar.gz files are decompressed to image.tar."""
        raw = b"hello-image"
        compressed = gzip.compress(raw)

        comp = _make_cia_component(
            "https://example.com/image.tar.gz",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        _patch_cia_download(monkeypatch, compressed)

        comp.download_hook()

        image_tar = Path(comp.component_tmp_dir) / "extracted" / "image.tar"
        assert image_tar.exists()
        assert image_tar.read_bytes() == raw

    def test_download_tgz(self, monkeypatch, tmp_path, arch_info):
        """.tgz files are decompressed to image.tar."""
        raw = b"hello-image-tgz"
        compressed = gzip.compress(raw)

        comp = _make_cia_component(
            "https://example.com/image.tgz",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        _patch_cia_download(monkeypatch, compressed)

        comp.download_hook()

        image_tar = Path(comp.component_tmp_dir) / "extracted" / "image.tar"
        assert image_tar.exists()
        assert image_tar.read_bytes() == raw

    def test_download_tar_xz(self, monkeypatch, tmp_path, arch_info):
        """.tar.xz files are decompressed to image.tar."""
        raw = b"hello-image-xz"
        compressed = lzma.compress(raw)

        comp = _make_cia_component(
            "https://example.com/image.tar.xz",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        _patch_cia_download(monkeypatch, compressed)

        comp.download_hook()

        image_tar = Path(comp.component_tmp_dir) / "extracted" / "image.tar"
        assert image_tar.exists()
        assert image_tar.read_bytes() == raw

    def test_download_txz(self, monkeypatch, tmp_path, arch_info):
        """.txz files are decompressed to image.tar."""
        raw = b"hello-image-txz"
        compressed = lzma.compress(raw)

        comp = _make_cia_component(
            "https://example.com/image.txz",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        _patch_cia_download(monkeypatch, compressed)

        comp.download_hook()

        image_tar = Path(comp.component_tmp_dir) / "extracted" / "image.tar"
        assert image_tar.exists()
        assert image_tar.read_bytes() == raw

    def test_download_tar_bz2(self, monkeypatch, tmp_path, arch_info):
        """.tar.bz2 files are decompressed to image.tar."""
        raw = b"hello-image-bz2"
        compressed = bz2.compress(raw)

        comp = _make_cia_component(
            "https://example.com/image.tar.bz2",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        _patch_cia_download(monkeypatch, compressed)

        comp.download_hook()

        image_tar = Path(comp.component_tmp_dir) / "extracted" / "image.tar"
        assert image_tar.exists()
        assert image_tar.read_bytes() == raw

    def test_download_unsupported_format_raises(self, monkeypatch, tmp_path, arch_info):
        """Unsupported archive format raises ComponentError."""
        comp = _make_cia_component(
            "https://example.com/image.rar",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        _patch_cia_download(monkeypatch, b"data")

        with pytest.raises(ComponentError, match="Unsupported archive format"):
            comp.download_hook()

    def test_download_local_source(self, monkeypatch, tmp_path, arch_info):
        """.tar files from local:// source resolve to file:// via download_file."""
        comp = _make_cia_component(
            "{{ repo.base-url }}/image.tar",
            base_url="local://fixtures",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"tar-content")

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.container_image_archive.download_file",
            fake_download,
        )

        comp.download_hook()

        assert len(calls) == 1
        assert calls[0].startswith("file://")
        image_tar = Path(comp.component_tmp_dir) / "extracted" / "image.tar"
        assert image_tar.exists()

    def test_download_gh_artifact(self, monkeypatch, tmp_path, arch_info):
        """.tar files from gh-artifact:// pass URL unchanged to download_file."""
        comp = _make_cia_component(
            "{{ repo.base-url }}/image.tar",
            base_url="gh-artifact://artifact-name",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"tar-content")

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.container_image_archive.download_file",
            fake_download,
        )

        comp.download_hook()

        assert len(calls) == 1
        assert calls[0].startswith("gh-artifact://")


# ===========================================================================
# container_manifest.py — remaining branch coverage
# ===========================================================================


def _make_manifest_component(
    base_url: str,
    source_format: str,
    monkeypatch,
    tmp_path: Path,
    arch_info,
) -> ComponentBase:
    repo = RepoInfo(base_url=base_url)
    install = InstallConfig(
        method=InstallMethod.CONTAINER_MANIFEST,
        source_format=source_format,
        bin_path="./*",
        repo=repo,
    )
    config = ComponentConfig(name="calico", category="cni", release="3.30.0", installation=install)
    manifest = _make_manifest()

    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, n: Path(tmp_path) / n / "temp"),
    )
    return ComponentBase({}, manifest, config, arch_info)


class TestContainerManifestRemainingBranches:
    def test_download_local_source(self, monkeypatch, tmp_path, arch_info):
        """_download resolves local:// base-url to file:// via download_file."""
        comp = _make_manifest_component(
            base_url="local://fixtures",
            source_format="{{ repo.base-url }}/calico.yaml",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("manifest: yaml")

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.container_manifest.download_file",
            fake_download,
        )

        comp.download_hook()

        assert len(calls) == 1
        assert calls[0].startswith("file://")
        assert comp.manifest_path is not None
        assert comp.manifest_path.exists()

    def test_download_gh_artifact(self, monkeypatch, tmp_path, arch_info):
        """_download passes gh-artifact:// URL unchanged to download_file."""
        comp = _make_manifest_component(
            base_url="gh-artifact://calico-manifest-artifact",
            source_format="{{ repo.base-url }}/calico.yaml",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("manifest: yaml")

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.container_manifest.download_file",
            fake_download,
        )

        comp.download_hook()

        assert len(calls) == 1
        assert calls[0].startswith("gh-artifact://")
        assert comp.manifest_path is not None

    def test_bootstrap_wraps_cluster_error(self, monkeypatch, tmp_path, arch_info):
        """_bootstrap raises ComponentError when apply_manifest raises ClusterError."""
        comp = _make_manifest_component(
            base_url="https://github.com/projectcalico/calico",
            source_format=(
                "raw.githubusercontent.com/projectcalico/calico/v{{ release }}/calico.yaml"
            ),
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )
        manifest_file = tmp_path / "calico" / "temp" / "calico-manifest.yaml"
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text("apiVersion: v1\n")
        comp.manifest_path = manifest_file

        def fake_apply(path: Path) -> None:
            raise ClusterError("kubectl apply failed")

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.container_manifest.apply_manifest",
            fake_apply,
        )

        with pytest.raises(ComponentError, match="Failed to apply manifest"):
            comp.bootstrap_hook()


# ===========================================================================
# spread.py — remaining branch coverage
# ===========================================================================


def _make_spread_component(
    base_url: str,
    source_format: str,
    monkeypatch,
    tmp_path: Path,
    arch_info,
) -> ComponentBase:
    repo = RepoInfo(base_url=base_url)
    install = InstallConfig(
        method=InstallMethod.NONE,
        source_format="",
        bin_path="",
        repo=RepoInfo(base_url="https://example.com"),
    )
    test_cfg = ComponentTestConfig(
        method=ComponentTestMethod.SPREAD,
        source_format=source_format,
        repo=repo,
    )
    config = ComponentConfig(
        name="mycomp",
        category="test",
        release="v1.0",
        installation=install,
        test=test_cfg,
    )
    manifest = _make_manifest()

    monkeypatch.setattr(
        SystemPaths,
        "component_temp_dir",
        classmethod(lambda cls, n: Path(tmp_path) / n / "temp"),
    )
    monkeypatch.setattr(
        SystemPaths,
        "tests_root",
        classmethod(lambda cls: Path(tmp_path) / "tests"),
    )
    ai = arch_info if arch_info is not None else get_arch_info()
    return ComponentBase({}, manifest, config, ai)


class TestSpreadRemainingBranches:
    def test_download_gh_artifact(self, monkeypatch, tmp_path, arch_info):
        """_download passes gh-artifact:// URL unchanged to download_file."""
        comp = _make_spread_component(
            base_url="gh-artifact://spread-suite-artifact",
            source_format="{{ repo.base-url }}/spread/kube-galaxy/task.yaml",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.spread.download_file", fake_download
        )

        comp.download_hook()

        assert len(calls) == 1
        assert calls[0].startswith("gh-artifact://")

    def test_download_remote_https(self, monkeypatch, tmp_path, arch_info):
        """_download passes https:// URL unchanged to download_file."""
        comp = _make_spread_component(
            base_url="https://github.com/org/repo",
            source_format="{{ repo.base-url }}/spread/kube-galaxy/task.yaml",
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            arch_info=arch_info,
        )

        calls: list = []

        def fake_download(url: str, dest: Path) -> None:
            calls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            "kube_galaxy.pkg.components.strategies.spread.download_file", fake_download
        )

        comp.download_hook()

        assert len(calls) == 1
        assert calls[0].startswith("https://")
