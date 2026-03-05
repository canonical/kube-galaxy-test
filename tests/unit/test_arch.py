"""Unit tests for architecture detector."""

import platform

import pytest

from kube_galaxy.pkg.arch.detector import (
    ArchInfo,
    detect_system_arch,
    get_arch_info,
    map_to_image_arch,
    map_to_k8s_arch,
)


def test_detect_system_arch():
    """Test system architecture detection."""
    arch = detect_system_arch()
    assert isinstance(arch, str)
    assert len(arch) > 0
    assert arch == platform.machine()


def test_map_to_k8s_arch_amd64():
    """Test mapping x86_64 to K8s amd64."""
    assert map_to_k8s_arch("x86_64") == "amd64"
    assert map_to_k8s_arch("amd64") == "amd64"


def test_map_to_k8s_arch_arm64():
    """Test mapping aarch64/arm64 to K8s arm64."""
    assert map_to_k8s_arch("aarch64") == "arm64"
    assert map_to_k8s_arch("arm64") == "arm64"


def test_map_to_k8s_arch_riscv64():
    """Test mapping riscv64."""
    assert map_to_k8s_arch("riscv64") == "riscv64"


def test_map_to_k8s_arch_arm():
    """Test mapping armv7l/armv6l to arm."""
    assert map_to_k8s_arch("armv7l") == "arm"
    assert map_to_k8s_arch("armv6l") == "arm"


def test_map_to_k8s_arch_ppc64le():
    """Test mapping ppc64le."""
    assert map_to_k8s_arch("ppc64le") == "ppc64le"


def test_map_to_k8s_arch_s390x():
    """Test mapping s390x."""
    assert map_to_k8s_arch("s390x") == "s390x"


def test_map_to_k8s_arch_unsupported():
    """Test error for unsupported architecture."""
    with pytest.raises(ValueError, match="Unsupported architecture"):
        map_to_k8s_arch("mips64")


def test_map_to_image_arch_amd64():
    """Test mapping x86_64 to image amd64."""
    assert map_to_image_arch("x86_64") == "amd64"


def test_map_to_image_arch_arm():
    """Test mapping arm architectures to image tags."""
    assert map_to_image_arch("aarch64") == "arm64"
    assert map_to_image_arch("armv7l") == "armv7"
    assert map_to_image_arch("armv6l") == "armv6"


def test_map_to_image_arch_unsupported():
    """Test error for unsupported image architecture."""
    with pytest.raises(ValueError, match="Unsupported architecture"):
        map_to_image_arch("unknown_arch")


def test_get_arch_info():
    """Test getting complete architecture info."""
    info = get_arch_info()

    assert isinstance(info, ArchInfo)
    assert info.system == platform.machine()
    assert isinstance(info.k8s, str)
    assert isinstance(info.image, str)
    assert len(info.k8s) > 0
    assert len(info.image) > 0


def test_arch_info_consistency():
    """Test that arch info fields are consistent."""
    info = get_arch_info()

    # All fields should match expected mappings
    assert info.k8s == map_to_k8s_arch(info.system)
    assert info.image == map_to_image_arch(info.system)
