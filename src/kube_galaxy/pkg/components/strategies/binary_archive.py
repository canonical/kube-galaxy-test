"""Install hooks for InstallMethod.BINARY_ARCHIVE."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from kube_galaxy.pkg.literals import Permissions, SystemPaths
from kube_galaxy.pkg.utils.components import format_component_pattern
from kube_galaxy.pkg.utils.errors import ComponentError

from ._base import _fetch_to_temp, _InstallStrategy

if TYPE_CHECKING:
    from kube_galaxy.pkg.components._base import ComponentBase


def _bin_path(comp: ComponentBase) -> str:
    return format_component_pattern(
        comp.config.installation.bin_path,
        comp.config,
        comp.arch_info,
        comp.config.installation.repo,
    )


def _download(comp: ComponentBase) -> None:
    # Download archive to the orchestrator staging area only; no local extraction needed.
    # Extraction is deferred to the install phase and performed on each node.
    comp.binary_path = _fetch_to_temp(comp)


def _install(comp: ComponentBase) -> None:
    if not comp.binary_path or not comp.binary_path.exists():
        raise ComponentError(f"{comp.name} archive not downloaded. Run download hook first.")

    archive_path = comp.binary_path
    node_temp_dir = SystemPaths.component_temp_dir(comp.name)
    node_archive = str(node_temp_dir / archive_path.name)
    node_extracted_dir = str(node_temp_dir / "extracted")

    # Transfer the archive from the orchestrator staging area to the node and extract it there.
    archive_url = comp.unit.staging_url(archive_path)
    comp.unit.download(archive_url, node_archive)
    comp.unit.extract(node_archive, node_extracted_dir)

    # Find and install matching binaries from the extracted location on the node.
    bin_pattern = _bin_path(comp)
    node_bin_dir = SystemPaths.component_bin_dir(comp.name)
    comp.unit.run(["mkdir", "-p", str(node_bin_dir)], privileged=True)

    result = comp.unit.run(
        [
            "sh",
            "-c",
            f"for f in {node_extracted_dir}/{bin_pattern}; "
            f'do [ -f "$f" ] && printf \'%s\\n\' "$f"; done',
        ],
        check=False,
    )

    for binary_file in result.stdout.splitlines():
        binary_file = binary_file.strip()
        if not binary_file:
            continue
        binary_name = Path(binary_file).name
        dest = str(node_bin_dir / binary_name)
        comp.unit.run(["mv", binary_file, dest], privileged=True)
        comp.unit.run(["chmod", "755", dest], privileged=True)
        alternative_path = f"{SystemPaths.USR_LOCAL_BIN}/{binary_name}"
        comp.unit.run(
            [
                "update-alternatives",
                "--install",
                alternative_path,
                binary_name,
                dest,
                Permissions.ALTERNATIVES_PRIORITY,
            ],
            privileged=True,
        )
        if binary_name == comp.name:
            comp.install_path = alternative_path

    # Clean up the archive and extracted directory on the node after installation.
    comp.unit.run(
        ["rm", "-rf", node_archive, node_extracted_dir], privileged=True, check=False
    )


_BinaryArchiveInstallStrategy = _InstallStrategy(download=_download, install=_install)
