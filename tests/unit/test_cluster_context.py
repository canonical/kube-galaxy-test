"""Unit tests for ClusterContext dataclass."""

from unittest.mock import MagicMock

from kube_galaxy.pkg.cluster_context import ClusterContext


class TestClusterContextDefaults:
    def test_components_default_is_empty_dict(self) -> None:
        ctx = ClusterContext()
        assert ctx.components == {}

    def test_artifact_server_default_is_none(self) -> None:
        ctx = ClusterContext()
        assert ctx.artifact_server is None

    def test_registry_mirror_default_is_none(self) -> None:
        ctx = ClusterContext()
        assert ctx.registry_mirror is None

    def test_components_not_shared_between_instances(self) -> None:
        ctx1 = ClusterContext()
        ctx2 = ClusterContext()
        ctx1.components["a"] = MagicMock()
        assert "a" not in ctx2.components


class TestClusterContextMutations:
    def test_can_add_component(self) -> None:
        ctx = ClusterContext()
        comp = MagicMock()
        ctx.components["kubeadm"] = comp
        assert ctx.components["kubeadm"] is comp

    def test_can_set_artifact_server(self) -> None:
        ctx = ClusterContext()
        server = MagicMock()
        ctx.artifact_server = server
        assert ctx.artifact_server is server

    def test_can_clear_artifact_server(self) -> None:
        ctx = ClusterContext()
        ctx.artifact_server = MagicMock()
        ctx.artifact_server = None
        assert ctx.artifact_server is None

    def test_can_set_registry_mirror(self) -> None:
        ctx = ClusterContext()
        mirror = MagicMock()
        ctx.registry_mirror = mirror
        assert ctx.registry_mirror is mirror

    def test_can_clear_registry_mirror(self) -> None:
        ctx = ClusterContext()
        ctx.registry_mirror = MagicMock()
        ctx.registry_mirror = None
        assert ctx.registry_mirror is None

    def test_components_explicit_dict(self) -> None:
        comp = MagicMock()
        ctx = ClusterContext(components={"kubeadm": comp})
        assert ctx.components["kubeadm"] is comp
        assert ctx.artifact_server is None
        assert ctx.registry_mirror is None
