"""GitHub Actions integration utilities.

Provides helper functions for outputting values to GitHub Actions workflow
environments using the GITHUB_OUTPUT mechanism for inter-step communication.
"""

import os

# GitHub Actions sets this environment variable pointing to the output file
GITHUB_OUTPUT = os.getenv("GITHUB_OUTPUT")


def gh_output(name: str, value: str) -> None:
    """Output a value for use in subsequent GitHub Actions workflow steps.

    Writes key-value pairs to the GITHUB_OUTPUT file, enabling communication
    between different steps in a GitHub Actions workflow. If GITHUB_OUTPUT
    is not set (e.g., running outside GitHub Actions), this function is a no-op.

    Args:
        name: The output variable name (used as the key in workflow context)
        value: The output value to set (accessible as steps.<step-id>.outputs.<name>)

    Example:
        gh_output("cluster_id", "my-cluster-123")
        # In subsequent workflow steps: ${{ steps.<step-id>.outputs.cluster_id }}
    """
    if GITHUB_OUTPUT:
        with open(GITHUB_OUTPUT, "a") as f:
            f.write(f"{name}={value}\n")
