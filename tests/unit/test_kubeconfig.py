"""Unit tests for pkg/utils/kubeconfig.py."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from kube_galaxy.pkg.utils.kubeconfig import (
    KUBE_GALAXY_CONTEXT,
    context_exists,
    is_interactive,
    merge_kube_galaxy_context,
    remove_kube_galaxy_context,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_kubeconfig(path: Path, config: dict[str, Any]) -> None:
    """Write *config* as a YAML kubeconfig to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        yaml.dump(config, fh, default_flow_style=False)


def _read_kubeconfig(path: Path) -> dict[str, Any]:
    with path.open() as fh:
        return yaml.safe_load(fh)  # type: ignore[no-any-return]


def _minimal_source_kubeconfig(cluster_name: str = "kube-galaxy-cluster") -> dict[str, Any]:
    """Return a minimal kubeconfig dict as produced by kubeadm/kube-galaxy setup."""
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": cluster_name,
                "cluster": {
                    "server": "https://10.0.0.1:6443",
                    "certificate-authority-data": "CERTDATA",
                },
            }
        ],
        "contexts": [
            {
                "name": "default",
                "context": {
                    "cluster": cluster_name,
                    "user": "admin",
                    "namespace": "default",
                },
            }
        ],
        "users": [
            {
                "name": "admin",
                "user": {
                    "client-certificate-data": "CLIENTCERT",
                    "client-key-data": "CLIENTKEY",
                },
            }
        ],
        "current-context": "default",
        "preferences": {},
    }


def _minimal_dest_kubeconfig(other_context: str = "other") -> dict[str, Any]:
    """Return a kubeconfig dict that already has one context (*other_context*)."""
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": other_context,
                "cluster": {"server": "https://192.168.1.1:6443"},
            }
        ],
        "contexts": [
            {
                "name": other_context,
                "context": {"cluster": other_context, "user": other_context},
            }
        ],
        "users": [
            {
                "name": other_context,
                "user": {"token": "sometoken"},
            }
        ],
        "current-context": other_context,
        "preferences": {},
    }


# ---------------------------------------------------------------------------
# context_exists
# ---------------------------------------------------------------------------


def test_context_exists_returns_false_when_no_file(tmp_path: Path) -> None:
    dest = tmp_path / ".kube" / "config"
    assert not context_exists(KUBE_GALAXY_CONTEXT, config_path=dest)


def test_context_exists_returns_false_when_context_absent(tmp_path: Path) -> None:
    dest = tmp_path / "config"
    _write_kubeconfig(dest, _minimal_dest_kubeconfig("other"))
    assert not context_exists(KUBE_GALAXY_CONTEXT, config_path=dest)


def test_context_exists_returns_true_when_present(tmp_path: Path) -> None:
    dest = tmp_path / "config"
    cfg = _minimal_dest_kubeconfig("other")
    cfg["contexts"].append({"name": KUBE_GALAXY_CONTEXT, "context": {}})
    _write_kubeconfig(dest, cfg)
    assert context_exists(KUBE_GALAXY_CONTEXT, config_path=dest)


# ---------------------------------------------------------------------------
# merge_kube_galaxy_context
# ---------------------------------------------------------------------------


def test_merge_creates_new_kubeconfig_when_dest_absent(tmp_path: Path) -> None:
    src = tmp_path / "src_kubeconfig"
    dest = tmp_path / ".kube" / "config"
    _write_kubeconfig(src, _minimal_source_kubeconfig())

    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    assert dest.exists()
    config = _read_kubeconfig(dest)
    ctx_names = [c["name"] for c in config["contexts"]]
    assert KUBE_GALAXY_CONTEXT in ctx_names
    assert config["current-context"] == KUBE_GALAXY_CONTEXT


def test_merge_renames_cluster_and_user_to_context_name(tmp_path: Path) -> None:
    src = tmp_path / "src_kubeconfig"
    dest = tmp_path / "dest_kubeconfig"
    _write_kubeconfig(src, _minimal_source_kubeconfig())

    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    config = _read_kubeconfig(dest)
    cluster_names = [c["name"] for c in config["clusters"]]
    user_names = [u["name"] for u in config["users"]]
    ctx = next(c for c in config["contexts"] if c["name"] == KUBE_GALAXY_CONTEXT)

    assert KUBE_GALAXY_CONTEXT in cluster_names
    assert KUBE_GALAXY_CONTEXT in user_names
    assert ctx["context"]["cluster"] == KUBE_GALAXY_CONTEXT
    assert ctx["context"]["user"] == KUBE_GALAXY_CONTEXT


def test_merge_preserves_existing_contexts(tmp_path: Path) -> None:
    src = tmp_path / "src_kubeconfig"
    dest = tmp_path / "dest_kubeconfig"
    _write_kubeconfig(src, _minimal_source_kubeconfig())
    _write_kubeconfig(dest, _minimal_dest_kubeconfig("prod"))

    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    config = _read_kubeconfig(dest)
    ctx_names = {c["name"] for c in config["contexts"]}
    assert "prod" in ctx_names
    assert KUBE_GALAXY_CONTEXT in ctx_names


def test_merge_sets_current_context(tmp_path: Path) -> None:
    src = tmp_path / "src_kubeconfig"
    dest = tmp_path / "dest_kubeconfig"
    _write_kubeconfig(src, _minimal_source_kubeconfig())
    _write_kubeconfig(dest, _minimal_dest_kubeconfig("other"))

    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    config = _read_kubeconfig(dest)
    assert config["current-context"] == KUBE_GALAXY_CONTEXT


def test_merge_replaces_existing_kube_galaxy_context(tmp_path: Path) -> None:
    src = tmp_path / "src_kubeconfig"
    dest = tmp_path / "dest_kubeconfig"
    _write_kubeconfig(src, _minimal_source_kubeconfig())

    # Merge twice — the second call should not duplicate entries
    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)
    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    config = _read_kubeconfig(dest)
    assert len([c for c in config["contexts"] if c["name"] == KUBE_GALAXY_CONTEXT]) == 1
    assert len([c for c in config["clusters"] if c["name"] == KUBE_GALAXY_CONTEXT]) == 1
    assert len([u for u in config["users"] if u["name"] == KUBE_GALAXY_CONTEXT]) == 1


def test_merge_creates_parent_directories(tmp_path: Path) -> None:
    src = tmp_path / "src_kubeconfig"
    dest = tmp_path / "a" / "b" / "c" / "config"
    _write_kubeconfig(src, _minimal_source_kubeconfig())

    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    assert dest.exists()


def test_merge_raises_for_incomplete_source(tmp_path: Path) -> None:
    src = tmp_path / "bad_kubeconfig"
    dest = tmp_path / "dest"
    src.write_text("apiVersion: v1\nkind: Config\n")

    with pytest.raises(ValueError, match="missing required"):
        merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)


def test_merge_sets_restrictive_permissions(tmp_path: Path) -> None:
    src = tmp_path / "src_kubeconfig"
    dest = tmp_path / "dest_kubeconfig"
    _write_kubeconfig(src, _minimal_source_kubeconfig())

    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    assert oct(dest.stat().st_mode)[-3:] == "600"


# ---------------------------------------------------------------------------
# remove_kube_galaxy_context
# ---------------------------------------------------------------------------


def test_remove_is_noop_when_no_file(tmp_path: Path) -> None:
    dest = tmp_path / "nonexistent"
    remove_kube_galaxy_context(KUBE_GALAXY_CONTEXT, dest_path=dest)
    assert not dest.exists()


def test_remove_is_noop_when_context_absent(tmp_path: Path) -> None:
    dest = tmp_path / "config"
    cfg = _minimal_dest_kubeconfig("other")
    _write_kubeconfig(dest, cfg)

    remove_kube_galaxy_context(KUBE_GALAXY_CONTEXT, dest_path=dest)

    config = _read_kubeconfig(dest)
    assert len(config["contexts"]) == 1


def test_remove_deletes_file_when_last_context(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "config"
    _write_kubeconfig(src, _minimal_source_kubeconfig())
    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    # kube-galaxy is the only context — file should be deleted
    remove_kube_galaxy_context(KUBE_GALAXY_CONTEXT, dest_path=dest)

    assert not dest.exists()


def test_remove_keeps_file_when_other_contexts_exist(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "config"
    _write_kubeconfig(src, _minimal_source_kubeconfig())
    _write_kubeconfig(dest, _minimal_dest_kubeconfig("prod"))
    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    remove_kube_galaxy_context(KUBE_GALAXY_CONTEXT, dest_path=dest)

    assert dest.exists()
    config = _read_kubeconfig(dest)
    ctx_names = {c["name"] for c in config["contexts"]}
    assert KUBE_GALAXY_CONTEXT not in ctx_names
    assert "prod" in ctx_names


def test_remove_updates_current_context_when_removed(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "config"
    _write_kubeconfig(src, _minimal_source_kubeconfig())
    _write_kubeconfig(dest, _minimal_dest_kubeconfig("prod"))
    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    # current-context is now kube-galaxy; after removal it should switch to "prod"
    remove_kube_galaxy_context(KUBE_GALAXY_CONTEXT, dest_path=dest)

    config = _read_kubeconfig(dest)
    assert config["current-context"] == "prod"


def test_remove_also_removes_associated_cluster_and_user(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "config"
    _write_kubeconfig(src, _minimal_source_kubeconfig())
    _write_kubeconfig(dest, _minimal_dest_kubeconfig("prod"))
    merge_kube_galaxy_context(src, context_name=KUBE_GALAXY_CONTEXT, dest_path=dest)

    remove_kube_galaxy_context(KUBE_GALAXY_CONTEXT, dest_path=dest)

    config = _read_kubeconfig(dest)
    cluster_names = {c["name"] for c in config["clusters"]}
    user_names = {u["name"] for u in config["users"]}
    assert KUBE_GALAXY_CONTEXT not in cluster_names
    assert KUBE_GALAXY_CONTEXT not in user_names


def test_remove_preserves_other_contexts_current_context_unchanged(tmp_path: Path) -> None:
    """If current-context is 'prod' (not kube-galaxy), it should not change."""
    src = tmp_path / "src"
    dest = tmp_path / "config"
    _write_kubeconfig(src, _minimal_source_kubeconfig())
    # Start with prod as current-context, then merge kube-galaxy (makes it current)
    dest_cfg = _minimal_dest_kubeconfig("prod")
    _write_kubeconfig(dest, dest_cfg)

    # Manually add kube-galaxy but keep prod as current-context
    dest_cfg2 = _read_kubeconfig(dest)
    dest_cfg2["contexts"].append(
        {
            "name": KUBE_GALAXY_CONTEXT,
            "context": {"cluster": KUBE_GALAXY_CONTEXT, "user": KUBE_GALAXY_CONTEXT},
        }
    )
    dest_cfg2["clusters"].append(
        {"name": KUBE_GALAXY_CONTEXT, "cluster": {"server": "https://1.2.3.4:6443"}}
    )
    dest_cfg2["users"].append({"name": KUBE_GALAXY_CONTEXT, "user": {}})
    # Keep current-context = "prod"
    dest_cfg2["current-context"] = "prod"
    _write_kubeconfig(dest, dest_cfg2)

    remove_kube_galaxy_context(KUBE_GALAXY_CONTEXT, dest_path=dest)

    config = _read_kubeconfig(dest)
    assert config["current-context"] == "prod"


# ---------------------------------------------------------------------------
# is_interactive
# ---------------------------------------------------------------------------


def test_is_interactive_returns_bool() -> None:
    result = is_interactive()
    assert isinstance(result, bool)


def test_is_interactive_false_when_stdin_not_tty() -> None:
    with patch("kube_galaxy.pkg.utils.kubeconfig.sys") as mock_sys:
        mock_sys.stdin.isatty.return_value = False
        assert not is_interactive()


def test_is_interactive_true_when_stdin_is_tty() -> None:
    with patch("kube_galaxy.pkg.utils.kubeconfig.sys") as mock_sys:
        mock_sys.stdin.isatty.return_value = True
        assert is_interactive()
