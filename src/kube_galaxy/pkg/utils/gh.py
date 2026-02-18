"""GitHub Actions integration utilities.

Provides helper functions for outputting values to GitHub Actions workflow
environments using the GITHUB_OUTPUT mechanism for inter-step communication.
"""

import os
import uuid

# GitHub Actions sets this environment variable pointing to the output file
GITHUB_OUTPUT = os.getenv("GITHUB_OUTPUT")


def gh_output(name: str, value: str) -> None:
    """Output a value for use in subsequent GitHub Actions workflow steps.

    Writes key-value pairs to the GITHUB_OUTPUT file, enabling communication
    between different steps in a GitHub Actions workflow. If GITHUB_OUTPUT
    is not set (e.g., running outside GitHub Actions), this function is a no-op.

    GitHub Actions requires multiline values to be written using the EOF
    delimiter syntax. If `value` contains newlines this function will write
    the value using a unique delimiter to avoid breaking the workflow.

    Args:
        name: The output variable name (used as the key in workflow context)
        value: The output value to set (accessible as steps.<step-id>.outputs.<name>)

    Example:
        gh_output("cluster_id", "my-cluster-123")
        # In subsequent workflow steps: ${{ steps.<step-id>.outputs.cluster_id }}
    """
    if not GITHUB_OUTPUT:
        return

    # Single-line values can be written in the simple key=value form.
    if "\n" not in value:
        with open(GITHUB_OUTPUT, "a") as f:
            f.write(f"{name}={value}\n")
        return

    # For multiline values use the EOF delimiter form. Choose a delimiter
    # that is unlikely to appear in the value (UUID-based) to be safe.
    delim = f"DELIM_{uuid.uuid4().hex}"
    with open(GITHUB_OUTPUT, "a") as f:
        f.write(f"{name}<<{delim}\n")
        f.write(value)
        # Ensure a trailing newline before the closing delimiter.
        if not value.endswith("\n"):
            f.write("\n")
        f.write(f"{delim}\n")
