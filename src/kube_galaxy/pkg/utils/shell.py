"""Shell subprocess execution wrapper."""

import shutil
import subprocess
from typing import Any

from kube_galaxy.pkg.utils.logging import success, warning


class ShellError(Exception):
    """Shell command execution error."""

    def __init__(self, command: list[str], returncode: int, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"Command failed with code {returncode}: {' '.join(command)}\n{stderr}")


def run(
    command: list[str],
    check: bool = True,
    capture_output: bool = False,
    text: bool = True,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command safely.

    Args:
        command: Command and arguments as list
        check: Raise ShellError on non-zero exit
        capture_output: Capture stdout/stderr
        text: Return output as strings
        **kwargs: Additional arguments to subprocess.run

    Returns:
        CompletedProcess instance

    Raises:
        ShellError: If check=True and command fails
    """
    result = subprocess.run(
        command,
        capture_output=capture_output,
        text=text,
        check=False,
        **kwargs,
    )

    if check and result.returncode != 0:
        stderr = result.stderr or ""
        raise ShellError(command, result.returncode, stderr)

    return result


def check_installed(cmd: str) -> None:
    """Check if a command is installed and return status."""
    if not shutil.which(cmd):
        raise ShellError([cmd], 1, f"❌ {cmd} not installed")
    success(f"{cmd} is installed")


def check_version(cmd: str) -> None:
    """Check if a command is installed and return its version."""
    check_installed(cmd)
    try:
        if cmd == "kubectl":
            result = run(
                [cmd, "version", "--client"],
                capture_output=True,
                check=False,
            )
        elif cmd == "ssh":
            result = run(
                [cmd, "-V"],
                capture_output=True,
                check=False,
            )
        else:
            result = run(
                [cmd, "--version"],
                capture_output=True,
                check=False,
            )

        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            success(f"{cmd} version: {version}")
        else:
            warning(f"{cmd} version check failed: {result.stderr.strip()}")
    except Exception:
        warning(f"{cmd} version check error")
