"""Unit tests for cluster.py provider wiring.

Verifies that setup_cluster and teardown_cluster engage provider_factory
and pass the provisioned unit to every component.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kube_galaxy.pkg.cluster import setup_cluster, teardown_cluster
from kube_galaxy.pkg.cluster_context import ClusterContext
from kube_galaxy.pkg.manifest.models import (
    Manifest,
    NodeRole,
    NodesConfig,
    ProviderConfig,
)
from kube_galaxy.pkg.units._base import UnitProvider
from kube_galaxy.pkg.units.local import LocalUnit, LocalUnitProvider
from kube_galaxy.pkg.units.lxdvm import LXDUnit, LXDUnitProvider
from kube_galaxy.pkg.units.multipass import MultipassUnit, MultipassUnitProvider
from kube_galaxy.pkg.units.provider import (
    provider_factory,
)
from kube_galaxy.pkg.units.ssh import SSHUnitProvider
from kube_galaxy.pkg.units.vsphere import VSphereUnitProvider
from tests.unit.components.conftest import MockUnit

# ---------------------------------------------------------------------------
# provider_factory dispatch
# ---------------------------------------------------------------------------


def _manifest_with_provider(provider_type: str, **kwargs: Any) -> Manifest:
    """Build a minimal Manifest with a specific provider type."""
    cfg = ProviderConfig(type=provider_type, **kwargs)
    return Manifest(name="t", kubernetes_version="1.35.0", provider=cfg)


def test_provider_factory_local():
    m = _manifest_with_provider("local")
    p = provider_factory(m)
    assert isinstance(p, LocalUnitProvider)
    assert not p.is_ephemeral


def test_provider_factory_lxd():
    m = _manifest_with_provider("lxd", image="ubuntu:24.04")
    p = provider_factory(m)
    assert isinstance(p, LXDUnitProvider)
    assert p.is_ephemeral


def test_provider_factory_multipass(monkeypatch):
    monkeypatch.setattr("kube_galaxy.pkg.units.multipass.check_version", lambda _cmd: None)
    m = _manifest_with_provider("multipass", image="ubuntu:24.04")
    p = provider_factory(m)
    assert isinstance(p, MultipassUnitProvider)
    assert p.is_ephemeral


def test_provider_factory_ssh():
    m = _manifest_with_provider("ssh", hosts=["10.0.0.1"])
    p = provider_factory(m)
    assert isinstance(p, SSHUnitProvider)
    assert not p.is_ephemeral


def test_provider_factory_unknown():
    m = _manifest_with_provider("nonexistent")
    with pytest.raises(ValueError, match="Unknown provider type"):
        provider_factory(m)


def test_provider_factory_vsphere(monkeypatch):
    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.check_version", lambda _cmd: None)
    monkeypatch.setattr("kube_galaxy.pkg.units.vsphere.check_installed", lambda _cmd: None)
    m = _manifest_with_provider(
        "vsphere",
        image="ubuntu-24.04-template",
        vsphere_datacenter="DC1",
        vsphere_datastore="datastore1",
        vsphere_network="VM Network",
    )
    p = provider_factory(m)
    assert isinstance(p, VSphereUnitProvider)
    assert p.is_ephemeral


def test_provider_factory_default_is_lxd():
    """Manifest with no provider block defaults to lxd."""
    m = Manifest(name="t", kubernetes_version="1.35.0")
    assert m.provider.type == "lxd"
    p = provider_factory(m)
    assert isinstance(p, LXDUnitProvider)


# ---------------------------------------------------------------------------
# LocalUnitProvider locate == provision (both return LocalUnit)
# ---------------------------------------------------------------------------


def test_local_provider_locate_returns_local_unit():
    p = LocalUnitProvider(NodesConfig(), "")
    u = p.locate(NodeRole.CONTROL_PLANE, 0)
    assert isinstance(u, LocalUnit)


def test_local_provider_provision_returns_local_unit():
    p = LocalUnitProvider(NodesConfig(), "")
    u = p.provision(NodeRole.CONTROL_PLANE, 0)
    assert isinstance(u, LocalUnit)


# ---------------------------------------------------------------------------
# LXDUnitProvider.locate — no subprocess, deterministic name, deduplication
# ---------------------------------------------------------------------------


def test_lxd_provider_locate_deterministic_name():
    p = LXDUnitProvider(NodesConfig(), image="ubuntu:24.04")
    u = p.locate(NodeRole.CONTROL_PLANE, 0)
    assert isinstance(u, LXDUnit)
    assert u.name == "kube-galaxy-control-plane-0"


def test_lxd_provider_locate_dedup():
    """locate_all called twice for the same counts adds only one entry per slot."""
    p = LXDUnitProvider(NodesConfig(), image="ubuntu:24.04")
    u1 = p.locate_all()[0]
    u2 = p.locate_all()[0]
    assert u1.name == u2.name
    assert len(p._units) == 1


def test_lxd_provider_locate_populates_units_for_deprovision_all(monkeypatch):
    """After locate_all, deprovision_all should call lxc delete for the located unit."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # type: ignore[misc]
        calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    p = LXDUnitProvider(NodesConfig(), image="ubuntu:24.04")
    p.locate_all()
    p.deprovision_all()

    assert any("kube-galaxy-control-plane-0" in " ".join(c) for c in calls)


# ---------------------------------------------------------------------------
# MultipassUnitProvider.locate — same behaviour as LXDUnitProvider.locate
# ---------------------------------------------------------------------------


def test_multipass_provider_locate_deterministic_name():
    p = MultipassUnitProvider(NodesConfig(), image="ubuntu:24.04")
    u = p.locate(NodeRole.WORKER, 1)
    assert isinstance(u, MultipassUnit)
    assert u.name == "kube-galaxy-worker-1"


def test_multipass_provider_locate_dedup():
    p = MultipassUnitProvider(NodesConfig(), image="ubuntu:24.04")
    p.locate_all()
    p.locate_all()
    assert len(p._units) == 1


# ---------------------------------------------------------------------------
# setup_cluster provider wiring (integration-light, no real lifecycle hooks)
# ---------------------------------------------------------------------------


def _minimal_manifest(tmp_path: Path, provider_type: str = "local") -> Path:
    """Write a manifest YAML that has a single known component (kubeadm)."""
    content = f"""\
name: test-cluster
description: Provider wiring test
kubernetes-version: "1.35.0"
provider:
  type: {provider_type}
components:
  - name: kubeadm
    category: kubernetes
    release: "1.35.0"
    installation:
      method: binary
      source-format: "https://dl.k8s.io/v{{{{ release }}}}/bin/linux/amd64/kubeadm"
      bin-path: ./kubeadm
"""
    p = tmp_path / "manifest.yaml"
    p.write_text(content)
    return p


def test_setup_cluster_calls_provision_all(monkeypatch, tmp_path):
    """setup_cluster must call provider.provision_all."""
    manifest_path = _minimal_manifest(tmp_path, "local")

    mock_provider = MagicMock(spec=UnitProvider)

    def capturing_component(ctx, manifest, config, arch_info, unit=None):  # type: ignore[misc]
        obj = MagicMock()
        obj.is_cluster_manager = True
        for hook in [
            "download_hook",
            "pre_install_hook",
            "install_hook",
            "configure_hook",
            "bootstrap_hook",
            "verify_hook",
        ]:
            setattr(obj, hook, MagicMock())
        return obj

    with (
        patch("kube_galaxy.pkg.cluster.provider_factory", return_value=mock_provider),
        patch("kube_galaxy.pkg.cluster.find_component", return_value=capturing_component),
        patch("kube_galaxy.pkg.cluster.ArtifactServer"),
        patch("kube_galaxy.pkg.cluster.RegistryMirror"),
        patch("kube_galaxy.pkg.cluster.gh_output"),
    ):
        setup_cluster(str(manifest_path))

    mock_provider.provision_all.assert_called_once()


def test_teardown_cluster_calls_locate_all(monkeypatch, tmp_path):
    """teardown_cluster must call provider.locate_all (not provision_all)."""
    manifest_path = _minimal_manifest(tmp_path, "local")

    mock_provider = MagicMock(spec=UnitProvider)
    mock_provider.is_ephemeral = False

    def capturing_component(ctx, manifest, config, arch_info, unit=None):  # type: ignore[misc]
        obj = MagicMock()
        for hook in ["stop_hook", "delete_hook", "post_delete_hook"]:
            setattr(obj, hook, MagicMock())
        return obj

    with (
        patch("kube_galaxy.pkg.cluster.provider_factory", return_value=mock_provider),
        patch("kube_galaxy.pkg.cluster.find_component", return_value=capturing_component),
        patch("kube_galaxy.pkg.cluster.ArtifactServer"),
        patch("kube_galaxy.pkg.cluster.RegistryMirror"),
        patch("kube_galaxy.pkg.cluster.gh_output"),
        patch("kube_galaxy.pkg.cluster._cleanup_kube_galaxy_alternatives"),
    ):
        teardown_cluster(str(manifest_path))

    # locate_all (not provision_all) is called for teardown
    mock_provider.locate_all.assert_called_once()
    mock_provider.provision_all.assert_not_called()


def test_teardown_cluster_deprovisions_ephemeral(tmp_path):
    """For ephemeral providers, teardown_cluster calls deprovision_all."""
    manifest_path = _minimal_manifest(tmp_path, "local")

    located_unit = MockUnit(_name="ep-unit")
    mock_provider = MagicMock(spec=UnitProvider)
    mock_provider.locate.return_value = located_unit
    mock_provider.is_ephemeral = True

    def capturing_component(ctx, manifest, config, arch_info, unit=None):  # type: ignore[misc]
        obj = MagicMock()
        for hook in ["stop_hook", "delete_hook", "post_delete_hook"]:
            setattr(obj, hook, MagicMock())
        return obj

    with (
        patch("kube_galaxy.pkg.cluster.provider_factory", return_value=mock_provider),
        patch("kube_galaxy.pkg.cluster.find_component", return_value=capturing_component),
        patch("kube_galaxy.pkg.cluster.ArtifactServer"),
        patch("kube_galaxy.pkg.cluster.RegistryMirror"),
        patch("kube_galaxy.pkg.cluster.gh_output"),
        patch("kube_galaxy.pkg.cluster._cleanup_kube_galaxy_alternatives"),
    ):
        teardown_cluster(str(manifest_path))

    mock_provider.deprovision_all.assert_called_once()


# ---------------------------------------------------------------------------
# RegistryMirror lifecycle integration
# ---------------------------------------------------------------------------


def _capturing_component_for_setup():  # type: ignore[misc]
    """Return a capturing component factory suitable for full setup_cluster mocking."""

    def factory(ctx, manifest, config, arch_info, unit=None):  # type: ignore[misc]
        obj = MagicMock()
        obj.is_cluster_manager = True
        for hook in [
            "download_hook",
            "pre_install_hook",
            "install_hook",
            "configure_hook",
            "bootstrap_hook",
            "verify_hook",
        ]:
            setattr(obj, hook, MagicMock())
        return obj

    return factory


def test_setup_cluster_starts_registry_mirror_when_enabled(tmp_path):
    """setup_cluster calls mirror.start() when registry.enabled=True (default)."""
    manifest_path = _minimal_manifest(tmp_path)

    mock_provider = MagicMock(spec=UnitProvider)
    mock_provider.provision.return_value = MockUnit(_name="prov-unit")

    mock_mirror_instance = MagicMock()
    MockRegistryMirror = MagicMock(return_value=mock_mirror_instance)

    with (
        patch("kube_galaxy.pkg.cluster.provider_factory", return_value=mock_provider),
        patch(
            "kube_galaxy.pkg.cluster.find_component",
            return_value=_capturing_component_for_setup(),
        ),
        patch("kube_galaxy.pkg.cluster.ArtifactServer"),
        patch("kube_galaxy.pkg.cluster.RegistryMirror", MockRegistryMirror),
        patch("kube_galaxy.pkg.cluster.gh_output"),
    ):
        setup_cluster(str(manifest_path))

    MockRegistryMirror.assert_called_once()
    mock_mirror_instance.start.assert_called_once()
    mock_mirror_instance.stop.assert_not_called()


def test_setup_cluster_skips_registry_mirror_when_disabled(tmp_path):
    """setup_cluster uses nullcontext (not RegistryMirror) when registry.enabled=False."""
    content = """\
name: test-cluster
description: Mirror-disabled test
kubernetes-version: "1.35.0"
provider:
  type: local
artifact:
  registry:
    enabled: false
components:
  - name: kubeadm
    category: kubernetes
    release: "1.35.0"
    installation:
      method: binary
      source-format: "https://dl.k8s.io/v{{ release }}/bin/linux/amd64/kubeadm"
      bin-path: ./kubeadm
"""
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(content)

    mock_provider = MagicMock(spec=UnitProvider)
    mock_provider.provision.return_value = MockUnit(_name="prov-unit")

    MockRegistryMirror = MagicMock()

    with (
        patch("kube_galaxy.pkg.cluster.provider_factory", return_value=mock_provider),
        patch(
            "kube_galaxy.pkg.cluster.find_component",
            return_value=_capturing_component_for_setup(),
        ),
        patch("kube_galaxy.pkg.cluster.ArtifactServer"),
        patch("kube_galaxy.pkg.cluster.RegistryMirror", MockRegistryMirror),
        patch("kube_galaxy.pkg.cluster.gh_output"),
    ):
        setup_cluster(str(manifest_path))

    MockRegistryMirror.assert_not_called()


def test_teardown_cluster_stops_registry_mirror_when_enabled(tmp_path):
    """teardown_cluster calls mirror.stop() after hooks when registry.enabled=True."""
    manifest_path = _minimal_manifest(tmp_path)

    located_unit = MockUnit(_name="loc-unit")
    mock_provider = MagicMock(spec=UnitProvider)
    mock_provider.locate.return_value = located_unit
    mock_provider.is_ephemeral = False

    def capturing_component(ctx, manifest, config, arch_info, unit=None):  # type: ignore[misc]
        obj = MagicMock()
        for hook in ["stop_hook", "delete_hook", "post_delete_hook"]:
            setattr(obj, hook, MagicMock())
        return obj

    mock_mirror_instance = MagicMock()
    MockRegistryMirror = MagicMock(return_value=mock_mirror_instance)

    with (
        patch("kube_galaxy.pkg.cluster.provider_factory", return_value=mock_provider),
        patch("kube_galaxy.pkg.cluster.find_component", return_value=capturing_component),
        patch("kube_galaxy.pkg.cluster.ArtifactServer"),
        patch("kube_galaxy.pkg.cluster.RegistryMirror", MockRegistryMirror),
        patch("kube_galaxy.pkg.cluster.gh_output"),
        patch("kube_galaxy.pkg.cluster._cleanup_kube_galaxy_alternatives"),
    ):
        teardown_cluster(str(manifest_path))

    MockRegistryMirror.assert_called_once()
    mock_mirror_instance.stop.assert_called_once()
    mock_mirror_instance.start.assert_not_called()


def test_setup_cluster_wires_ctx_services(tmp_path):
    """setup_cluster wires ctx.registry_mirror and clears ctx.artifact_server after setup."""
    manifest_path = _minimal_manifest(tmp_path)

    mock_provider = MagicMock(spec=UnitProvider)
    mock_provider.provision.return_value = MockUnit(_name="prov-unit")

    captured_ctxs: list[ClusterContext] = []

    def factory(ctx, manifest, config, arch_info, unit=None):  # type: ignore[misc]
        captured_ctxs.append(ctx)
        obj = MagicMock()
        obj.is_cluster_manager = True
        for hook in [
            "download_hook",
            "pre_install_hook",
            "install_hook",
            "configure_hook",
            "bootstrap_hook",
            "verify_hook",
        ]:
            setattr(obj, hook, MagicMock())
        return obj

    mock_mirror_instance = MagicMock()
    MockRegistryMirror = MagicMock(return_value=mock_mirror_instance)

    with (
        patch("kube_galaxy.pkg.cluster.provider_factory", return_value=mock_provider),
        patch("kube_galaxy.pkg.cluster.find_component", return_value=factory),
        patch("kube_galaxy.pkg.cluster.ArtifactServer"),
        patch("kube_galaxy.pkg.cluster.RegistryMirror", MockRegistryMirror),
        patch("kube_galaxy.pkg.cluster.gh_output"),
    ):
        setup_cluster(str(manifest_path))

    assert len(captured_ctxs) == 1
    ctx = captured_ctxs[0]
    assert ctx.registry_mirror is mock_mirror_instance
    assert ctx.artifact_server is None
