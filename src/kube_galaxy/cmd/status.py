"""Status command handler."""

import shutil
import subprocess
from pathlib import Path

from kube_galaxy.pkg.utils.logging import info, print_dict, section


def status() -> None:
    """Display project status including dependencies and file counts."""
    section("Kubernetes Galaxy Test - Project Status")

    # Check dependencies
    info("Dependencies:")
    deps = {
        "kubectl": check_command("kubectl"),
        "kubeadm": check_command("kubeadm"),
        "yq": check_command("yq"),
        "spread": check_command("spread"),
    }
    print_dict(deps)

    # Count project files
    info("")
    info("Project Files:")
    file_counts = {
        "Manifests": len(list(Path("manifests").glob("*.yaml")))
        if Path("manifests").exists()
        else 0,
        "Workflows": len(
            list(Path(".github/workflows").glob("*.yml"))
            + list(Path(".github/workflows").glob("*.yaml"))
        )
        if Path(".github/workflows").exists()
        else 0,
        "Actions": len(
            list(Path(".github/actions").glob("*/action.yml"))
            + list(Path(".github/actions").glob("*/action.yaml"))
        )
        if Path(".github/actions").exists()
        else 0,
        "Tests": len(list(Path("tests").glob("*.yaml")) + list(Path("tests").glob("*.yml")))
        if Path("tests").exists()
        else 0,
    }
    print_dict(file_counts)

    # Show kubeadm cluster nodes
    if shutil.which("kubectl"):
        info("")
        try:
            result = subprocess.run(
                ["kubectl", "get", "nodes"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split("\n")
                info(f"Cluster Nodes: {len(lines) - 1}")  # Subtract header
                for line in lines[1:]:  # Skip header
                    if line:
                        info(f"    {line}")
        except Exception:
            pass

    # Show active cluster
    if shutil.which("kubectl"):
        info("")
        try:
            result = subprocess.run(
                ["kubectl", "config", "current-context"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                context = result.stdout.strip()
                info(f"Active Cluster: {context}")
            else:
                info("Active Cluster: none")
        except Exception:
            info("Active Cluster: error checking")


def check_command(cmd: str) -> str:
    """Check if a command is installed and return status."""
    if shutil.which(cmd):
        try:
            if cmd == "kubectl":
                result = subprocess.run(
                    [cmd, "version", "--client"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            elif cmd == "kubeadm":
                result = subprocess.run(
                    [cmd, "version"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            else:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    text=True,
                    check=False,
                )

            if result.returncode == 0:
                version = result.stdout.strip().split("\n")[0]
                return f"✅ {version}"
            else:
                return "⚠️  installed (version check failed)"
        except Exception:
            return "⚠️  installed (version check error)"
    else:
        return "❌ not installed"
