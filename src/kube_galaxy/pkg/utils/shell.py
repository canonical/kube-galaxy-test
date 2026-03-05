"""Shell subprocess execution wrapper."""

import subprocess
from typing import Any


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
