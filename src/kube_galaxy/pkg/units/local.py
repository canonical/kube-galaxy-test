"""LocalUnit  executes operations on the local machine.

This is the backward-compatible null-object default used when no ``provider``
block is present in the manifest.  All component code that previously called
``shell.run()`` directly now calls ``self.unit.run()``; for ``LocalUnit`` the
behaviour is identical to before with the addition that ``privileged=True``
prepends ``sudo`` automatically when not running as root.
"""

import os
import shutil
import subprocess
import zipfile
from functools import cached_property
from pathlib import Path

from kube_galaxy.pkg.arch.detector import ArchInfo, get_arch_info
from kube_galaxy.pkg.units._base import RunResult, SiteCredential, Unit
from kube_galaxy.pkg.utils.errors import ComponentError
from kube_galaxy.pkg.utils.shell import ShellError

_CREDENTIALS_DIR = Path("/opt/kube-galaxy/credentials")


class LocalUnit(Unit):
    """Unit that executes operations directly on the local machine.

    Privilege model:
    - Running as root: all commands execute as-is.
    - Running as non-root: ``privileged=True`` prepends ``sudo``.
    """

    @property
    def name(self) -> str:
        return "local"

    @cached_property
    def arch(self) -> ArchInfo:
        return get_arch_info()

    def run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        privileged: bool = False,
        timeout: float | None = None,
    ) -> RunResult:
        effective_cmd = list(cmd)
        if privileged and os.getuid() != 0:
            effective_cmd = ["sudo", *effective_cmd]

        result = subprocess.run(
            effective_cmd,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise ShellError(effective_cmd, result.returncode, result.stderr or "")
        return RunResult(
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

    def put(self, local: Path, remote: str) -> None:
        dest = Path(remote)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, dest)

    def get(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(remote), local)

    def download(self, url: str, dest: str) -> None:
        # Import here to avoid circular import: local.py  components.py  units/_base.py
        from kube_galaxy.pkg.utils.components import download_file  # noqa: PLC0415

        download_file(url, Path(dest))

    def extract(self, archive: str, dest: str) -> None:
        from kube_galaxy.pkg.utils.components import extract_archive  # noqa: PLC0415

        extract_archive(Path(archive), Path(dest))

    def extract_zip(self, zip_file: str, path_in_zip: str, dest: str) -> None:
        try:
            with zipfile.ZipFile(zip_file) as zf:
                data = zf.read(path_in_zip)
            dest_path = Path(dest)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(data)
        except Exception as e:
            raise ComponentError(f"Failed to extract '{path_in_zip}' from '{zip_file}': {e}") from e

    def sha256(self, path: str) -> str:
        from kube_galaxy.pkg.utils.components import compute_sha256  # noqa: PLC0415

        return compute_sha256(Path(path))

    def enlist(self, credentials: list[SiteCredential]) -> None:
        _CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        for cred in credentials:
            curlrc = _CREDENTIALS_DIR / f"{cred.hostname}.curlrc"
            curlrc.write_text(f'header = "Authorization: {cred.auth_header}"\n')
            curlrc.chmod(0o600)

    def release(self) -> None:
        if _CREDENTIALS_DIR.exists():
            shutil.rmtree(_CREDENTIALS_DIR)

    def wait_until_ready(self, timeout: float | None = None) -> None:
        """Local unit is always ready; nothing to wait for."""
