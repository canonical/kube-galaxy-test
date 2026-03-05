"""Unit tests for Kubernetes client operations wrapper."""

import json
from unittest.mock import MagicMock

import pytest

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


class TestVerifyConnectivity:
    """Tests for verify_connectivity()."""

    def test_verify_connectivity_success(self, monkeypatch):
        """Test successful cluster connectivity verification."""
        mock_which = MagicMock(return_value=True)
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.shutil.which", mock_which)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        verify_connectivity()

        mock_which.assert_called_once_with("kubectl")
        mock_run.assert_called_once_with(
            ["kubectl", "cluster-info"], check=True, capture_output=True
        )

    def test_verify_connectivity_kubectl_not_found(self, monkeypatch):
        """Test error when kubectl is not available."""
        mock_which = MagicMock(return_value=None)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.shutil.which", mock_which)

        with pytest.raises(ClusterError, match="kubectl not found in PATH"):
            verify_connectivity()

    def test_verify_connectivity_cluster_error(self, monkeypatch):
        """Test error when cluster connection fails."""
        mock_which = MagicMock(return_value=True)
        mock_run = MagicMock(
            side_effect=ShellError(["kubectl", "cluster-info"], 1, "Connection refused")
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.shutil.which", mock_which)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to connect to cluster"):
            verify_connectivity()


class TestGetContext:
    """Tests for get_context()."""

    def test_get_context_success(self, monkeypatch):
        """Test successful retrieval of current context."""
        result = MagicMock()
        result.stdout = "docker-desktop\n"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        context = get_context()

        assert context == "docker-desktop"
        mock_run.assert_called_once_with(
            ["kubectl", "config", "current-context"], check=True, capture_output=True, text=True
        )

    def test_get_context_error(self, monkeypatch):
        """Test error when context cannot be determined."""
        mock_run = MagicMock(
            side_effect=ShellError(["kubectl", "config", "current-context"], 1, "Config error")
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to get current context"):
            get_context()


class TestWaitForNodes:
    """Tests for wait_for_nodes()."""

    def test_wait_for_nodes_success(self, monkeypatch):
        """Test successful node readiness wait."""
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        wait_for_nodes(timeout=300, condition="Ready")

        mock_run.assert_called_once_with(
            [
                "kubectl",
                "wait",
                "--for=condition=Ready",
                "nodes",
                "--all",
                "--timeout=300s",
            ],
            check=True,
            capture_output=True,
        )

    def test_wait_for_nodes_custom_condition(self, monkeypatch):
        """Test wait with custom condition."""
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        wait_for_nodes(timeout=120, condition="Scheduled")

        mock_run.assert_called_once()
        args, _kwargs = mock_run.call_args
        assert "--for=condition=Scheduled" in args[0]
        assert "--timeout=120s" in args[0]

    def test_wait_for_nodes_timeout_error(self, monkeypatch):
        """Test timeout error when nodes don't reach condition."""
        mock_run = MagicMock(
            side_effect=ShellError(
                ["kubectl", "wait", "--for=condition=Ready", "nodes", "--all", "--timeout=300s"],
                124,
                "Timeout",
            )
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Nodes failed to reach Ready condition"):
            wait_for_nodes()


class TestWaitForPods:
    """Tests for wait_for_pods()."""

    def test_wait_for_pods_success(self, monkeypatch):
        """Test successful pod readiness wait."""
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        wait_for_pods(namespace="kube-system", timeout=300, condition="Ready")

        mock_run.assert_called_once_with(
            [
                "kubectl",
                "wait",
                "--for=condition=Ready",
                "pod",
                "--all",
                "-n",
                "kube-system",
                "--timeout=300s",
            ],
            check=True,
            capture_output=True,
        )

    def test_wait_for_pods_custom_namespace(self, monkeypatch):
        """Test wait for pods in custom namespace."""
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        wait_for_pods(namespace="default", timeout=60)

        args, _kwargs = mock_run.call_args
        assert "-n" in args[0]
        assert "default" in args[0]

    def test_wait_for_pods_error(self, monkeypatch):
        """Test error when pods don't reach condition."""
        mock_run = MagicMock(
            side_effect=ShellError(
                [
                    "kubectl",
                    "wait",
                    "--for=condition=Ready",
                    "pod",
                    "--all",
                    "-n",
                    "kube-system",
                    "--timeout=300s",
                ],
                1,
                "Pod failed",
            )
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Pods in kube-system failed to reach Ready"):
            wait_for_pods()


class TestGetApiServerStatus:
    """Tests for get_api_server_status()."""

    def test_get_api_server_status_success(self, monkeypatch):
        """Test successful API server readiness check."""
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        get_api_server_status(timeout=300)

        mock_run.assert_called_once_with(
            [
                "kubectl",
                "get",
                "--raw=/readyz",
                "--request-timeout=300s",
            ],
            check=True,
            capture_output=True,
        )

    def test_get_api_server_status_custom_timeout(self, monkeypatch):
        """Test API server check with custom timeout."""
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        get_api_server_status(timeout=120)

        args, _kwargs = mock_run.call_args
        assert "--request-timeout=120s" in args[0]

    def test_get_api_server_status_error(self, monkeypatch):
        """Test error when API server is not ready."""
        mock_run = MagicMock(
            side_effect=ShellError(
                ["kubectl", "get", "--raw=/readyz", "--request-timeout=300s"], 1, "Not ready"
            )
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="API server not ready"):
            get_api_server_status()


class TestGetClusterInfo:
    """Tests for get_cluster_info()."""

    def test_get_cluster_info_success(self, monkeypatch):
        """Test successful cluster info retrieval."""
        result = MagicMock()
        result.stdout = "Kubernetes control plane is running at https://localhost:6443"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        info = get_cluster_info()

        assert "Kubernetes control plane" in info
        mock_run.assert_called_once_with(
            ["kubectl", "cluster-info"], check=True, capture_output=True, text=True
        )

    def test_get_cluster_info_error(self, monkeypatch):
        """Test error when cluster info cannot be retrieved."""
        mock_run = MagicMock(
            side_effect=ShellError(["kubectl", "cluster-info"], 1, "Connection failed")
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to retrieve cluster info"):
            get_cluster_info()


class TestGetNodes:
    """Tests for get_nodes()."""

    def test_get_nodes_success(self, monkeypatch):
        """Test successful nodes retrieval."""
        result = MagicMock()
        result.stdout = (
            "NAME       STATUS   ROLES           AGE\nnode1      Ready    control-plane   5d"
        )
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        nodes = get_nodes()

        assert "node1" in nodes
        mock_run.assert_called_once_with(
            ["kubectl", "get", "nodes"], check=True, capture_output=True, text=True
        )

    def test_get_nodes_with_wide_output(self, monkeypatch):
        """Test nodes retrieval with wide output."""
        result = MagicMock()
        result.stdout = "NAME       STATUS   ROLES   AGE   INTERNAL-IP"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        get_nodes(wide=True)

        args, _kwargs = mock_run.call_args
        assert "-o" in args[0]
        assert "wide" in args[0]

    def test_get_nodes_error(self, monkeypatch):
        """Test error when nodes cannot be retrieved."""
        mock_run = MagicMock(side_effect=ShellError(["kubectl", "get", "nodes"], 1, "No nodes"))
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to retrieve nodes"):
            get_nodes()


class TestGetPods:
    """Tests for get_pods()."""

    def test_get_pods_all_namespaces(self, monkeypatch):
        """Test pods retrieval from all namespaces."""
        result = MagicMock()
        result.stdout = "NAMESPACE     NAME                            READY   STATUS"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        pods = get_pods()

        assert "NAMESPACE" in pods
        args, _kwargs = mock_run.call_args
        assert "-A" in args[0]

    def test_get_pods_specific_namespace(self, monkeypatch):
        """Test pods retrieval from specific namespace."""
        result = MagicMock()
        result.stdout = "NAME                    READY   STATUS"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        get_pods(namespace="default")

        args, _kwargs = mock_run.call_args
        assert "-n" in args[0]
        assert "default" in args[0]

    def test_get_pods_with_wide_output(self, monkeypatch):
        """Test pods retrieval with wide output."""
        result = MagicMock()
        result.stdout = "NAME   READY   STATUS   IP"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        get_pods(wide=True)

        args, _kwargs = mock_run.call_args
        assert "-o" in args[0]
        assert "wide" in args[0]

    def test_get_pods_with_format(self, monkeypatch):
        """Test pods retrieval with specific output format."""
        result = MagicMock()
        result.stdout = "[]"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        get_pods(output_format="json")

        args, _kwargs = mock_run.call_args
        assert "-o" in args[0]
        assert "json" in args[0]

    def test_get_pods_error(self, monkeypatch):
        """Test error when pods cannot be retrieved."""
        mock_run = MagicMock(side_effect=ShellError(["kubectl", "get", "pods", "-A"], 1, "No pods"))
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to retrieve pods"):
            get_pods()


class TestGetPodDataJson:
    """Tests for get_pod_data_json()."""

    def test_get_pod_data_json_success(self, monkeypatch):
        """Test successful JSON pod data retrieval."""
        result = MagicMock()
        pod_data = {
            "items": [
                {"metadata": {"name": "pod1", "namespace": "default"}},
                {"metadata": {"name": "pod2", "namespace": "default"}},
            ]
        }
        result.stdout = json.dumps(pod_data)
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        pods = get_pod_data_json()

        assert len(pods) == 2
        assert pods[0]["metadata"]["name"] == "pod1"

    def test_get_pod_data_json_empty(self, monkeypatch):
        """Test JSON pod data with empty results."""
        result = MagicMock()
        result.stdout = '{"items": []}'
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        pods = get_pod_data_json()

        assert pods == []

    def test_get_pod_data_json_specific_namespace(self, monkeypatch):
        """Test JSON pod data from specific namespace."""
        result = MagicMock()
        result.stdout = '{"items": []}'
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        get_pod_data_json(namespace="kube-system")

        args, _kwargs = mock_run.call_args
        assert "-n" in args[0]
        assert "kube-system" in args[0]

    def test_get_pod_data_json_shell_error(self, monkeypatch):
        """Test error when pod data cannot be retrieved."""
        mock_run = MagicMock(
            side_effect=ShellError(
                ["kubectl", "get", "pods", "-A", "-o", "json"], 1, "Connection failed"
            )
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to retrieve pods data"):
            get_pod_data_json()

    def test_get_pod_data_json_parse_error(self, monkeypatch):
        """Test error when JSON cannot be parsed."""
        result = MagicMock()
        result.stdout = "invalid json"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to retrieve pods data"):
            get_pod_data_json()


class TestDescribeNodes:
    """Tests for describe_nodes()."""

    def test_describe_nodes_success(self, monkeypatch):
        """Test successful node description retrieval."""
        result = MagicMock()
        result.stdout = "Name:               node1\nStatus:             Ready"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        desc = describe_nodes()

        assert "node1" in desc
        mock_run.assert_called_once_with(
            ["kubectl", "describe", "nodes"], check=True, capture_output=True, text=True
        )

    def test_describe_nodes_error(self, monkeypatch):
        """Test error when node descriptions cannot be retrieved."""
        mock_run = MagicMock(
            side_effect=ShellError(["kubectl", "describe", "nodes"], 1, "No nodes")
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to describe nodes"):
            describe_nodes()


class TestGetEvents:
    """Tests for get_events()."""

    def test_get_events_all_namespaces(self, monkeypatch):
        """Test events retrieval from all namespaces."""
        result = MagicMock()
        result.stdout = "NAMESPACE   NAME   REASON"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        events = get_events()

        assert "NAMESPACE" in events
        args, _kwargs = mock_run.call_args
        assert "-A" in args[0]

    def test_get_events_specific_namespace(self, monkeypatch):
        """Test events retrieval from specific namespace."""
        result = MagicMock()
        result.stdout = "NAME   REASON"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        get_events(namespace="default", all_namespaces=False)

        args, _kwargs = mock_run.call_args
        assert "-n" in args[0]
        assert "default" in args[0]

    def test_get_events_error(self, monkeypatch):
        """Test error when events cannot be retrieved."""
        mock_run = MagicMock(
            side_effect=ShellError(["kubectl", "get", "events", "-A"], 1, "No events")
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to retrieve events"):
            get_events()


class TestGetPodLogs:
    """Tests for get_pod_logs()."""

    def test_get_pod_logs_success(self, monkeypatch):
        """Test successful pod logs retrieval."""
        result = MagicMock()
        result.returncode = 0
        result.stdout = "Container started\nListening on port 8080"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        logs = get_pod_logs("default", "my-pod")

        assert "Container started" in logs
        mock_run.assert_called_once_with(
            ["kubectl", "logs", "-n", "default", "my-pod", "--tail=100"],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_get_pod_logs_custom_tail(self, monkeypatch):
        """Test pod logs with custom tail lines."""
        result = MagicMock()
        result.returncode = 0
        result.stdout = "Last 50 lines"
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        get_pod_logs("default", "my-pod", tail=50)

        args, _kwargs = mock_run.call_args
        assert "--tail=50" in args[0]

    def test_get_pod_logs_no_logs(self, monkeypatch):
        """Test pod logs when pod has no logs (non-zero exit)."""
        result = MagicMock()
        result.returncode = 1
        result.stdout = ""
        mock_run = MagicMock(return_value=result)
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        logs = get_pod_logs("default", "my-pod")

        assert logs == ""


class TestCreateNamespace:
    """Tests for create_namespace()."""

    def test_create_namespace_success(self, monkeypatch):
        """Test successful namespace creation."""
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        create_namespace("test-ns")

        calls = mock_run.call_args_list
        assert len(calls) == 1
        assert "kubectl" in calls[0][0][0]
        assert "create" in calls[0][0][0]
        assert "namespace" in calls[0][0][0]
        assert "test-ns" in calls[0][0][0]

    def test_create_namespace_with_labels(self, monkeypatch):
        """Test namespace creation with labels."""
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        create_namespace("test-ns", labels={"app": "test", "env": "dev"})

        calls = mock_run.call_args_list
        assert len(calls) == 2
        # Second call should be label command
        assert "label" in calls[1][0][0]
        assert "app=test" in calls[1][0][0]
        assert "env=dev" in calls[1][0][0]

    def test_create_namespace_error(self, monkeypatch):
        """Test error when namespace creation fails."""
        mock_run = MagicMock(
            side_effect=ShellError(
                ["kubectl", "create", "namespace", "test-ns"], 1, "Already exists"
            )
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to create namespace test-ns"):
            create_namespace("test-ns")


class TestDeleteNamespace:
    """Tests for delete_namespace()."""

    def test_delete_namespace_success(self, monkeypatch):
        """Test successful namespace deletion."""
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        delete_namespace("test-ns")

        mock_run.assert_called_once()
        args, _kwargs = mock_run.call_args
        assert "kubectl" in args[0]
        assert "delete" in args[0]
        assert "namespace" in args[0]
        assert "test-ns" in args[0]
        assert "--timeout" in args[0]
        assert "60s" in args[0]

    def test_delete_namespace_custom_timeout(self, monkeypatch):
        """Test namespace deletion with custom timeout."""
        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        delete_namespace("test-ns", timeout=120)

        args, _kwargs = mock_run.call_args
        assert "120s" in args[0]

    def test_delete_namespace_not_found(self, monkeypatch):
        """Test deleting non-existent namespace (should not fail)."""
        mock_run = MagicMock(
            side_effect=ShellError(
                ["kubectl", "delete", "namespace", "test-ns", "--timeout", "60s"], 1, "not found"
            )
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        # Should not raise error for "not found"
        delete_namespace("test-ns")

    def test_delete_namespace_other_error(self, monkeypatch):
        """Test error on namespace deletion failure (not "not found")."""
        mock_run = MagicMock(
            side_effect=ShellError(
                ["kubectl", "delete", "namespace", "test-ns", "--timeout", "60s"],
                1,
                "Permission denied",
            )
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to delete namespace test-ns"):
            delete_namespace("test-ns")


class TestApplyManifest:
    """Tests for apply_manifest()."""

    def test_apply_manifest_success(self, monkeypatch, tmp_path):
        """Test successful manifest application."""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text("apiVersion: v1\nkind: Pod")

        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        apply_manifest(manifest_file)

        mock_run.assert_called_once()
        args, _kwargs = mock_run.call_args
        assert "kubectl" in args[0]
        assert "apply" in args[0]
        assert "-f" in args[0]
        assert str(manifest_file) in args[0]

    def test_apply_manifest_with_string_path(self, monkeypatch, tmp_path):
        """Test manifest application with string path."""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text("apiVersion: v1")

        mock_run = MagicMock()
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        apply_manifest(str(manifest_file))

        mock_run.assert_called_once()

    def test_apply_manifest_file_not_found(self, monkeypatch):
        """Test error when manifest file does not exist."""
        with pytest.raises(ClusterError, match="Manifest not found"):
            apply_manifest("/nonexistent/manifest.yaml")

    def test_apply_manifest_error(self, monkeypatch, tmp_path):
        """Test error when manifest application fails."""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text("apiVersion: v1")

        mock_run = MagicMock(
            side_effect=ShellError(
                ["kubectl", "apply", "-f", str(manifest_file)], 1, "Invalid manifest"
            )
        )
        monkeypatch.setattr("kube_galaxy.pkg.utils.client.run", mock_run)

        with pytest.raises(ClusterError, match="Failed to apply manifest"):
            apply_manifest(manifest_file)
