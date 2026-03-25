"""Architecture detection and mapping for kube-galaxy."""

import socket
from dataclasses import dataclass


@dataclass
class ArchInfo:
    """System architecture information."""

    system: str  # Raw uname output (e.g., x86_64, aarch64)
    k8s: str  # Kubernetes binary format (e.g., amd64, arm64)
    image: str  # Container image tag format (e.g., amd64, arm64)


# Mapping from system architecture to Kubernetes format
_K8S_ARCH_MAP = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "riscv64": "riscv64",
    "armv7l": "arm",
    "armv6l": "arm",
    "ppc64le": "ppc64le",
    "s390x": "s390x",
}

# Mapping from system architecture to container image tag format
_IMAGE_ARCH_MAP = {
    **_K8S_ARCH_MAP,  # Start with same mappings
    "armv7l": "armv7",
    "armv6l": "armv6",
}


def map_to_k8s_arch(system_arch: str) -> str:
    """Map system architecture to Kubernetes binary format.

    Args:
        system_arch: System architecture from uname -m

    Returns:
        Kubernetes binary format (amd64, arm64, riscv64, etc.)

    Raises:
        ValueError: If architecture is not supported
    """
    if system_arch not in _K8S_ARCH_MAP:
        raise ValueError(f"Unsupported architecture: {system_arch}")
    return _K8S_ARCH_MAP[system_arch]


def map_to_image_arch(system_arch: str) -> str:
    """Map system architecture to container image tag format.

    Args:
        system_arch: System architecture from uname -m

    Returns:
        Container image tag format (amd64, arm64, armv7, etc.)

    Raises:
        ValueError: If architecture is not supported
    """
    if system_arch not in _IMAGE_ARCH_MAP:
        raise ValueError(f"Unsupported architecture: {system_arch}")
    return _IMAGE_ARCH_MAP[system_arch]


def get_arch_info(system_arch: str) -> ArchInfo:
    """Get complete architecture information.

    Returns:
        ArchInfo with system, k8s, and image formats
    """
    return ArchInfo(
        system=system_arch,
        k8s=map_to_k8s_arch(system_arch),
        image=map_to_image_arch(system_arch),
    )


def detect_ip() -> str:
    """Detect the primary IP address of the orchestrator host.

    Uses a UDP socket trick — connecting to an external address without
    sending any data forces the OS to select the correct source interface,
    which reveals the local IP.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("1.1.1.1", 80))
        return str(s.getsockname()[0])
    finally:
        s.close()
