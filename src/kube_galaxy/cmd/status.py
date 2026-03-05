"""Status command handler."""

import shutil

import typer

from kube_galaxy.pkg.utils.logging import error, info, print_dict, section, success, warning
from kube_galaxy.pkg.utils.shell import ShellError, run


def status(wait: bool = False, timeout: int = 300) -> None:
    """Display project status and optionally verify cluster health."""
    section("Kubernetes Galaxy Test - Project Status")

    _print_dependency_status()
    _print_cluster_context()

    if wait:
        _verify_cluster_health(timeout)
        success("Cluster is healthy")


def _print_dependency_status() -> None:
    """Print required command dependency status."""
    info("Dependencies:")
    deps = {
        "kubectl": _check_command("kubectl"),
        "kubeadm": _check_command("kubeadm"),
        "spread": _check_command("spread"),
    }
    print_dict(deps)


def _print_cluster_context() -> None:
    """Print active cluster context and current node table if available."""
    if not shutil.which("kubectl"):
        warning("kubectl not available; skipping cluster checks")
        return

    info("")
    try:
        result = run(["kubectl", "config", "current-context"], capture_output=True, check=False)
        context = result.stdout.strip() if result.returncode == 0 else "none"
        info(f"Active Cluster: {context}")
    except Exception:
        info("Active Cluster: error checking")

    try:
        result = run(["kubectl", "get", "nodes"], capture_output=True, check=False)
        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split("\n")
            info(f"Cluster Nodes: {len(lines) - 1}")
            for line in lines[1:]:
                if line:
                    info(f"    {line}")
    except Exception:
        pass


def _verify_cluster_health(timeout: int) -> None:
    """Wait for cluster readiness and print summary tables."""
    if not shutil.which("kubectl"):
        error("kubectl is required for --wait health checks", show_traceback=False)
        raise typer.Exit(code=1)

    timeout_arg = f"--timeout={timeout}s"
    section("Cluster Health Verification")
    info("Waiting for nodes to be Ready...")

    try:
        run(
            ["kubectl", "wait", "--for=condition=Ready", "node", "--all", timeout_arg],
            capture_output=True,
        )
        run(
            [
                "kubectl",
                "wait",
                "--for=condition=Ready",
                "pod",
                "--all",
                "-n",
                "kube-system",
                timeout_arg,
            ],
            capture_output=True,
        )
    except ShellError as exc:
        if exc.stderr.strip():
            error(exc.stderr.strip(), show_traceback=False)
        error("Cluster readiness checks failed", show_traceback=False)
        raise typer.Exit(code=1) from exc

    _print_command_output(["kubectl", "cluster-info"], "Cluster Info")
    _print_command_output(["kubectl", "get", "nodes", "-o", "wide"], "Nodes")
    _print_command_output(["kubectl", "get", "pods", "-A", "-o", "wide"], "Pods")


def _print_command_output(command: list[str], title: str) -> None:
    """Run command and print its output with a section label."""
    info("")
    info(f"{title}:")
    try:
        result = run(command, capture_output=True)
        output = result.stdout.strip()
        if output:
            info(output)
    except ShellError as exc:
        if exc.stderr.strip():
            error(exc.stderr.strip(), show_traceback=False)
        error(f"Failed to run: {' '.join(command)}", show_traceback=False)
        raise typer.Exit(code=1) from exc


def _check_command(cmd: str) -> str:
    """Check if a command is installed and return status."""
    if shutil.which(cmd):
        try:
            if cmd == "kubectl":
                result = run(
                    [cmd, "version", "--client"],
                    capture_output=True,
                    check=False,
                )
            elif cmd == "kubeadm":
                result = run(
                    [cmd, "version"],
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
                return f"✅ {version}"
            else:
                return "⚠️  installed (version check failed)"
        except Exception:
            return "⚠️  installed (version check error)"
    else:
        return "❌ not installed"
