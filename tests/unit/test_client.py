"""Unit tests for Kubernetes client operations wrapper."""

import json
from unittest.mock import MagicMock, patch

import pytest

from kube_galaxy.pkg.literals import Ports
from kube_galaxy.pkg.units._base import RunResult
from kube_galaxy.pkg.utils.client import (
    apply_manifest,
    create_namespace,
    delete_namespace,
    describe_nodes,
    get_api_server_status,
    get_cluster_info,
    get_context,
    get_events,
    get_nodes,
    get_pod_data_json,
    get_pod_logs,
    get_pods,
    verify_connectivity,
    wait_for_nodes,
    wait_for_pods,
)
from kube_galaxy.pkg.utils.errors import ClusterError
from kube_galaxy.pkg.utils.shell import ShellError
from tests.unit.components.conftest import MockUnit


def _mock_unit(stdout: str = "", returncode: int = 0) -> MockUnit:
    """Return a MockUnit pre-loaded with a single RunResult."""
    u = MockUnit()
    u.set_run_results(RunResult(returncode, stdout, ""))
    return u


def _make_shell_error(cmd: list[str]) -> ShellError:
    return ShellError(cmd, 1, "command failed")


class TestVerifyConnectivity:
    """Tests for verify_connectivity()."""

    def test_verify_connectivity_success(self):
        """Test successful cluster connectivity verification."""
        unit = MockUnit()
        verify_connectivity(unit)
        # source calls kubectl(unit, "version", check=True)
        assert any("version" in cmd for cmd, _ in unit.run_calls)

    def test_verify_connectivity_cluster_error(self):
        """Test error when cluster connection fails."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "version"], 1, "Connection refused"),
        ):
            with pytest.raises(ClusterError, match="Failed to connect to cluster"):
                verify_connectivity(unit)


class TestGetContext:
    """Tests for get_context()."""

    def test_get_context_success(self):
        """Test successful retrieval of current context."""
        unit = _mock_unit(stdout="docker-desktop\n")
        context = get_context(unit)
        assert context == "docker-desktop"
        assert any("current-context" in cmd for cmd, _ in unit.run_calls)

    def test_get_context_error(self):
        """Test error when context cannot be determined."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "config", "current-context"], 1, "Config error"),
        ):
            with pytest.raises(ClusterError, match="Failed to get current context"):
                get_context(unit)


class TestWaitForNodes:
    """Tests for wait_for_nodes()."""

    def test_wait_for_nodes_success(self):
        """Test successful node readiness wait."""
        unit = MockUnit()
        wait_for_nodes(unit, timeout=300, condition="Ready")
        cmd, _ = unit.run_calls[0]
        assert "--for=condition=Ready" in cmd
        assert "--timeout=300s" in cmd
        assert "nodes" in cmd

    def test_wait_for_nodes_custom_condition(self):
        """Test wait with custom condition."""
        unit = MockUnit()
        wait_for_nodes(unit, timeout=120, condition="Scheduled")
        cmd, _ = unit.run_calls[0]
        assert "--for=condition=Scheduled" in cmd
        assert "--timeout=120s" in cmd

    def test_wait_for_nodes_timeout_error(self):
        """Test timeout error when nodes don't reach condition."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "wait"], 124, "Timeout"),
        ):
            with pytest.raises(ClusterError, match="Nodes failed to reach Ready condition"):
                wait_for_nodes(unit)


class TestWaitForPods:
    """Tests for wait_for_pods()."""

    def test_wait_for_pods_success(self):
        """Test successful pod readiness wait."""
        unit = MockUnit()
        wait_for_pods(unit, namespace="kube-system", timeout=300, condition="Ready")
        cmd, _ = unit.run_calls[0]
        assert "--for=condition=Ready" in cmd
        assert "--timeout=300s" in cmd
        assert "kube-system" in cmd

    def test_wait_for_pods_custom_namespace(self):
        """Test wait for pods in custom namespace."""
        unit = MockUnit()
        wait_for_pods(unit, namespace="default", timeout=60)
        cmd, _ = unit.run_calls[0]
        assert "-n" in cmd
        assert "default" in cmd

    def test_wait_for_pods_error(self):
        """Test error when pods don't reach condition."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "wait"], 1, "Pod failed"),
        ):
            with pytest.raises(ClusterError, match="Pods in kube-system failed to reach Ready"):
                wait_for_pods(unit)


class TestGetApiServerStatus:
    """Tests for get_api_server_status()."""

    def test_get_api_server_status_success(self):
        """Test successful API server readiness check."""
        unit = MockUnit()
        get_api_server_status(unit, timeout=300)
        cmd, _ = unit.run_calls[0]
        assert "--raw=/readyz" in cmd
        assert "--request-timeout=300s" in cmd

    def test_get_api_server_status_custom_timeout(self):
        """Test API server check with custom timeout."""
        unit = MockUnit()
        get_api_server_status(unit, timeout=120)
        cmd, _ = unit.run_calls[0]
        assert "--request-timeout=120s" in cmd

    def test_get_api_server_status_error(self):
        """Test error when API server is not ready."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "get"], 1, "Not ready"),
        ):
            with pytest.raises(ClusterError, match="API server not ready"):
                get_api_server_status(unit)


class TestGetClusterInfo:
    """Tests for get_cluster_info()."""

    def test_get_cluster_info_success(self):
        """Test successful cluster info retrieval."""
        unit = _mock_unit(
            stdout=f"Kubernetes control plane is running at https://localhost:{Ports.KUBE_API_SERVER}\n"
        )
        result = get_cluster_info(unit)
        assert "Kubernetes control plane" in result
        cmd, _ = unit.run_calls[0]
        assert "cluster-info" in cmd

    def test_get_cluster_info_error(self):
        """Test error when cluster info cannot be retrieved."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "cluster-info"], 1, "Connection failed"),
        ):
            with pytest.raises(ClusterError, match="Failed to retrieve cluster info"):
                get_cluster_info(unit)


class TestGetNodes:
    """Tests for get_nodes()."""

    def test_get_nodes_success(self):
        """Test successful nodes retrieval."""
        unit = _mock_unit(
            stdout="NAME       STATUS   ROLES           AGE\nnode1      Ready    control-plane   5d"
        )
        nodes = get_nodes(unit)
        assert "node1" in nodes
        cmd, _ = unit.run_calls[0]
        assert "get" in cmd
        assert "nodes" in cmd

    def test_get_nodes_with_wide_output(self):
        """Test nodes retrieval with wide output."""
        unit = _mock_unit(stdout="NAME       STATUS   ROLES   AGE   INTERNAL-IP")
        get_nodes(unit, wide=True)
        cmd, _ = unit.run_calls[0]
        assert "-o" in cmd
        assert "wide" in cmd

    def test_get_nodes_error(self):
        """Test error when nodes cannot be retrieved."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "get", "nodes"], 1, "No nodes"),
        ):
            with pytest.raises(ClusterError, match="Failed to retrieve nodes"):
                get_nodes(unit)


class TestGetPods:
    """Tests for get_pods()."""

    def test_get_pods_all_namespaces(self):
        """Test pods retrieval from all namespaces."""
        unit = _mock_unit(stdout="NAMESPACE     NAME                            READY   STATUS")
        pods = get_pods(unit)
        assert "NAMESPACE" in pods
        cmd, _ = unit.run_calls[0]
        assert "-A" in cmd

    def test_get_pods_specific_namespace(self):
        """Test pods retrieval from specific namespace."""
        unit = _mock_unit(stdout="NAME                    READY   STATUS")
        get_pods(unit, namespace="default")
        cmd, _ = unit.run_calls[0]
        assert "-n" in cmd
        assert "default" in cmd

    def test_get_pods_with_wide_output(self):
        """Test pods retrieval with wide output."""
        unit = _mock_unit(stdout="NAME   READY   STATUS   IP")
        get_pods(unit, wide=True)
        cmd, _ = unit.run_calls[0]
        assert "-o" in cmd
        assert "wide" in cmd

    def test_get_pods_with_format(self):
        """Test pods retrieval with specific output format."""
        unit = _mock_unit(stdout="[]")
        get_pods(unit, output_format="json")
        cmd, _ = unit.run_calls[0]
        assert "-o" in cmd
        assert "json" in cmd

    def test_get_pods_error(self):
        """Test error when pods cannot be retrieved."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "get", "pods", "-A"], 1, "No pods"),
        ):
            with pytest.raises(ClusterError, match="Failed to retrieve pods"):
                get_pods(unit)


class TestGetPodDataJson:
    """Tests for get_pod_data_json()."""

    def test_get_pod_data_json_success(self):
        """Test successful JSON pod data retrieval."""
        pod_data = {
            "items": [
                {"metadata": {"name": "pod1", "namespace": "default"}},
                {"metadata": {"name": "pod2", "namespace": "default"}},
            ]
        }
        unit = _mock_unit(stdout=json.dumps(pod_data))
        pods = get_pod_data_json(unit)
        assert len(pods) == 2
        assert pods[0]["metadata"]["name"] == "pod1"

    def test_get_pod_data_json_empty(self):
        """Test JSON pod data with empty results."""
        unit = _mock_unit(stdout='{"items": []}')
        pods = get_pod_data_json(unit)
        assert pods == []

    def test_get_pod_data_json_specific_namespace(self):
        """Test JSON pod data from specific namespace."""
        unit = _mock_unit(stdout='{"items": []}')
        get_pod_data_json(unit, namespace="kube-system")
        cmd, _ = unit.run_calls[0]
        assert "-n" in cmd
        assert "kube-system" in cmd

    def test_get_pod_data_json_shell_error(self):
        """Test error when pod data cannot be retrieved."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "get", "pods"], 1, "Connection failed"),
        ):
            with pytest.raises(ClusterError, match="Failed to retrieve pods"):
                get_pod_data_json(unit)

    def test_get_pod_data_json_parse_error(self):
        """Test error when JSON cannot be parsed."""
        unit = _mock_unit(stdout="invalid json")
        with pytest.raises(ClusterError, match="Failed to retrieve pods data"):
            get_pod_data_json(unit)


class TestDescribeNodes:
    """Tests for describe_nodes()."""

    def test_describe_nodes_success(self):
        """Test successful node description retrieval."""
        unit = _mock_unit(stdout="Name:               node1\nStatus:             Ready")
        desc = describe_nodes(unit)
        assert "node1" in desc
        cmd, _ = unit.run_calls[0]
        assert "describe" in cmd
        assert "nodes" in cmd

    def test_describe_nodes_error(self):
        """Test error when node descriptions cannot be retrieved."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "describe", "nodes"], 1, "No nodes"),
        ):
            with pytest.raises(ClusterError, match="Failed to describe nodes"):
                describe_nodes(unit)


class TestGetEvents:
    """Tests for get_events()."""

    def test_get_events_all_namespaces(self):
        """Test events retrieval from all namespaces."""
        unit = _mock_unit(stdout="NAMESPACE   NAME   REASON")
        events = get_events(unit)
        assert "NAMESPACE" in events
        cmd, _ = unit.run_calls[0]
        assert "-A" in cmd

    def test_get_events_specific_namespace(self):
        """Test events retrieval from specific namespace."""
        unit = _mock_unit(stdout="NAME   REASON")
        get_events(unit, namespace="default", all_namespaces=False)
        cmd, _ = unit.run_calls[0]
        assert "-n" in cmd
        assert "default" in cmd

    def test_get_events_error(self):
        """Test error when events cannot be retrieved."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "get", "events", "-A"], 1, "No events"),
        ):
            with pytest.raises(ClusterError, match="Failed to retrieve events"):
                get_events(unit)


class TestGetPodLogs:
    """Tests for get_pod_logs()."""

    def test_get_pod_logs_success(self):
        """Test successful pod logs retrieval."""
        unit = _mock_unit(stdout="Container started\nListening on port 8080")
        logs = get_pod_logs(unit, "default", "my-pod")
        assert "Container started" in logs
        cmd, _ = unit.run_calls[0]
        assert "logs" in cmd
        assert "default" in cmd
        assert "my-pod" in cmd
        assert "--tail=100" in cmd

    def test_get_pod_logs_custom_tail(self):
        """Test pod logs with custom tail lines."""
        unit = _mock_unit(stdout="Last 50 lines")
        get_pod_logs(unit, "default", "my-pod", tail=50)
        cmd, _ = unit.run_calls[0]
        assert "--tail=50" in cmd

    def test_get_pod_logs_no_logs(self):
        """Test pod logs when pod has no logs (non-zero exit)."""
        unit = MockUnit()
        unit.set_run_results(RunResult(1, "", ""))
        # MockUnit.run doesn't raise on non-zero; get_pod_logs checks returncode
        # patch kubectl to return a non-zero result
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("kube_galaxy.pkg.utils.client.kubectl", return_value=mock_result):
            logs = get_pod_logs(unit, "default", "my-pod")
        assert logs == ""


class TestCreateNamespace:
    """Tests for create_namespace()."""

    def test_create_namespace_success(self):
        """Test successful namespace creation."""
        unit = MockUnit()
        create_namespace(unit, "test-ns")
        cmd, _ = unit.run_calls[0]
        assert "kubectl" in cmd
        assert "create" in cmd
        assert "namespace" in cmd
        assert "test-ns" in cmd

    def test_create_namespace_with_labels(self):
        """Test namespace creation with labels."""
        unit = MockUnit()
        create_namespace(unit, "test-ns", labels={"app": "test", "env": "dev"})
        assert len(unit.run_calls) == 2
        label_cmd, _ = unit.run_calls[1]
        assert "label" in label_cmd
        assert "app=test" in label_cmd
        assert "env=dev" in label_cmd

    def test_create_namespace_error(self):
        """Test error when namespace creation fails."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(
                ["kubectl", "create", "namespace", "test-ns"], 1, "Already exists"
            ),
        ):
            with pytest.raises(ClusterError, match="Failed to create namespace test-ns"):
                create_namespace(unit, "test-ns")


class TestDeleteNamespace:
    """Tests for delete_namespace()."""

    def test_delete_namespace_success(self):
        """Test successful namespace deletion."""
        unit = MockUnit()
        delete_namespace(unit, "test-ns")
        cmd, _ = unit.run_calls[0]
        assert "kubectl" in cmd
        assert "delete" in cmd
        assert "namespace" in cmd
        assert "test-ns" in cmd
        assert "--timeout" in cmd
        assert "60s" in cmd

    def test_delete_namespace_custom_timeout(self):
        """Test namespace deletion with custom timeout."""
        unit = MockUnit()
        delete_namespace(unit, "test-ns", timeout=120)
        cmd, _ = unit.run_calls[0]
        assert "120s" in cmd

    def test_delete_namespace_not_found(self):
        """Test deleting non-existent namespace (should not fail)."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "delete", "namespace", "test-ns"], 1, "not found"),
        ):
            delete_namespace(unit, "test-ns")

    def test_delete_namespace_other_error(self):
        """Test error on namespace deletion failure (not 'not found')."""
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(
                ["kubectl", "delete", "namespace", "test-ns"], 1, "Permission denied"
            ),
        ):
            with pytest.raises(ClusterError, match="Failed to delete namespace test-ns"):
                delete_namespace(unit, "test-ns")


class TestApplyManifest:
    """Tests for apply_manifest()."""

    def test_apply_manifest_success(self, tmp_path):
        """Test successful manifest application."""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text("apiVersion: v1\nkind: Pod")
        unit = MockUnit()
        apply_manifest(unit, manifest_file)
        assert any("apply" in cmd for cmd, _ in unit.run_calls)

    def test_apply_manifest_with_string_path(self, tmp_path):
        """Test manifest application with string path."""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text("apiVersion: v1")
        unit = MockUnit()
        apply_manifest(unit, str(manifest_file))
        assert len(unit.run_calls) > 0

    def test_apply_manifest_file_not_found(self):
        """Test error when manifest file does not exist."""
        unit = MockUnit()
        with pytest.raises(ClusterError, match="Manifest not found"):
            apply_manifest(unit, "/nonexistent/manifest.yaml")

    def test_apply_manifest_error(self, tmp_path):
        """Test error when manifest application fails."""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text("apiVersion: v1")
        unit = MockUnit()
        with patch(
            "kube_galaxy.pkg.utils.client.kubectl",
            side_effect=ShellError(["kubectl", "apply"], 1, "Invalid manifest"),
        ):
            with pytest.raises(ClusterError, match="Failed to apply manifest"):
                apply_manifest(unit, manifest_file)
