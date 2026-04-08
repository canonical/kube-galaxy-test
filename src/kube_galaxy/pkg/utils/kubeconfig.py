"""Kubeconfig context management utilities for kube-galaxy."""

import copy
import socket
import sys
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "KUBE_GALAXY_CONTEXT",
    "context_exists",
    "host_ip",
    "is_interactive",
    "merge_kube_galaxy_context",
    "remove_kube_galaxy_context",
]

KUBE_GALAXY_CONTEXT = "kube-galaxy"

_HOME_KUBE_CONFIG = Path.home() / ".kube" / "config"


def host_ip() -> str:
    """Return the default IP address of the host.

    Uses a UDP connect to a public DNS address to determine which local
    interface would be used for outbound traffic — no packets are sent.
    Falls back to ``gethostbyname(gethostname())`` if the socket trick
    fails.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip: str = s.getsockname()[0]
            return ip
    except OSError:
        return str(socket.gethostbyname(socket.gethostname()))

_EMPTY_CONFIG: dict[str, Any] = {
    "apiVersion": "v1",
    "kind": "Config",
    "clusters": [],
    "contexts": [],
    "users": [],
    "current-context": "",
    "preferences": {},
}


def _read_kubeconfig(path: Path) -> dict[str, Any]:
    """Read a kubeconfig YAML file.

    Returns an empty config skeleton when the file does not exist.
    """
    if not path.exists():
        return copy.deepcopy(_EMPTY_CONFIG)
    with path.open() as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}
    return data


def _write_kubeconfig(config: dict[str, Any], path: Path) -> None:
    """Write *config* to *path*, creating parent directories as needed.

    The file is written with restrictive (0o600) permissions so that
    credentials are not world-readable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        yaml.dump(config, fh, default_flow_style=False)
    path.chmod(0o600)


def _replace_or_add(
    entries: list[dict[str, Any]], new_entry: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return *entries* with *new_entry* replacing any item with the same ``name``."""
    name = new_entry["name"]
    filtered = [item for item in entries if item.get("name") != name]
    filtered.append(new_entry)
    return filtered


def context_exists(
    context_name: str = KUBE_GALAXY_CONTEXT,
    config_path: Path | None = None,
) -> bool:
    """Return ``True`` if *context_name* exists in the kubeconfig at *config_path*.

    Args:
        context_name: The context name to look for (default: ``kube-galaxy``).
        config_path: Path to the kubeconfig file.  Defaults to
            ``$HOME/.kube/config``.

    Returns:
        ``True`` if the context is present, ``False`` otherwise.
    """
    path = config_path if config_path is not None else _HOME_KUBE_CONFIG
    if not path.exists():
        return False
    config = _read_kubeconfig(path)
    contexts: list[dict[str, Any]] = config.get("contexts") or []
    return any(c.get("name") == context_name for c in contexts)


def merge_kube_galaxy_context(
    source_path: Path,
    context_name: str = KUBE_GALAXY_CONTEXT,
    dest_path: Path | None = None,
) -> None:
    """Merge the cluster context from *source_path* into the home kubeconfig.

    The first cluster, context, and user entries found in *source_path* are
    renamed to *context_name* and merged into *dest_path* (which defaults to
    ``$HOME/.kube/config``).  The merged context is set as the
    ``current-context``.

    If *dest_path* does not exist it is created (together with its parent
    directory).

    Args:
        source_path: Path to the kubeconfig produced by ``kube-galaxy setup``
            (typically ``<project>/tmp/opt/kube-galaxy/tests/kubeconfig``).
        context_name: Name to use for the merged context/cluster/user entries.
        dest_path: Destination kubeconfig.  Defaults to ``$HOME/.kube/config``.

    Raises:
        ValueError: If *source_path* is missing required sections.
    """
    dest = dest_path if dest_path is not None else _HOME_KUBE_CONFIG

    source = _read_kubeconfig(source_path)

    src_clusters: list[dict[str, Any]] = source.get("clusters") or []
    src_contexts: list[dict[str, Any]] = source.get("contexts") or []
    src_users: list[dict[str, Any]] = source.get("users") or []

    if not src_clusters or not src_contexts or not src_users:
        raise ValueError(
            f"Source kubeconfig '{source_path}' is missing required "
            "clusters, contexts, or users sections."
        )

    src_cluster = src_clusters[0]
    src_context = src_contexts[0]
    src_user = src_users[0]

    # Build renamed entries
    cluster_entry: dict[str, Any] = {
        "name": context_name,
        "cluster": src_cluster.get("cluster") or {},
    }
    user_entry: dict[str, Any] = {
        "name": context_name,
        "user": src_user.get("user") or {},
    }
    context_entry: dict[str, Any] = {
        "name": context_name,
        "context": {
            **(src_context.get("context") or {}),
            "cluster": context_name,
            "user": context_name,
        },
    }

    # Read (or initialise) the destination kubeconfig
    dest_config = _read_kubeconfig(dest)
    for field in ("clusters", "contexts", "users"):
        if not dest_config.get(field):
            dest_config[field] = []

    dest_config["clusters"] = _replace_or_add(dest_config["clusters"], cluster_entry)
    dest_config["users"] = _replace_or_add(dest_config["users"], user_entry)
    dest_config["contexts"] = _replace_or_add(dest_config["contexts"], context_entry)
    dest_config["current-context"] = context_name

    _write_kubeconfig(dest_config, dest)


def remove_kube_galaxy_context(
    context_name: str = KUBE_GALAXY_CONTEXT,
    dest_path: Path | None = None,
) -> None:
    """Remove *context_name* from the home kubeconfig.

    The associated cluster and user entries (referenced by the context) are
    also removed.  If the context was the ``current-context``, the first
    remaining context (if any) is selected instead.

    If no contexts remain after the removal the kubeconfig file is deleted
    entirely.

    Args:
        context_name: The context to remove (default: ``kube-galaxy``).
        dest_path: Kubeconfig to modify.  Defaults to ``$HOME/.kube/config``.
    """
    dest = dest_path if dest_path is not None else _HOME_KUBE_CONFIG

    if not dest.exists():
        return

    config = _read_kubeconfig(dest)

    contexts: list[dict[str, Any]] = config.get("contexts") or []
    ctx_entry = next((c for c in contexts if c.get("name") == context_name), None)

    # Determine the cluster and user names referenced by this context
    ctx_cluster: str | None = None
    ctx_user: str | None = None
    if ctx_entry is not None:
        ctx_cluster = (ctx_entry.get("context") or {}).get("cluster")
        ctx_user = (ctx_entry.get("context") or {}).get("user")

    new_contexts = [c for c in contexts if c.get("name") != context_name]

    clusters: list[dict[str, Any]] = config.get("clusters") or []
    remove_cluster = ctx_cluster or context_name
    new_clusters = [c for c in clusters if c.get("name") != remove_cluster]

    users: list[dict[str, Any]] = config.get("users") or []
    remove_user = ctx_user or context_name
    new_users = [u for u in users if u.get("name") != remove_user]

    # If no contexts remain, remove the file entirely
    if not new_contexts:
        dest.unlink(missing_ok=True)
        return

    config["contexts"] = new_contexts
    config["clusters"] = new_clusters
    config["users"] = new_users

    # Update current-context if it pointed to the removed context
    if config.get("current-context") == context_name:
        config["current-context"] = new_contexts[0]["name"]

    _write_kubeconfig(config, dest)


def is_interactive() -> bool:
    """Return ``True`` when stdin is connected to a terminal (interactive session)."""
    return sys.stdin.isatty()
