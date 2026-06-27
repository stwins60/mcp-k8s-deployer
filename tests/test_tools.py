import pytest
from unittest.mock import patch, MagicMock
from src.tools import (
    choose_storage_option,
    deploy_app,
    plan_deployment,
    apply_deployment,
    create_namespace,
    get_service_endpoint,
    build_cloudflared_target
)

def test_choose_storage_option_nfs():
    res = choose_storage_option(storage_class="nfs", has_existing_pv=False, storage_size="5Gi")
    assert res["use_persistence"] is True
    assert res["pvc_needed"] is True
    assert res["existing_pv_name"] is None
    assert "matches the default NFS" in res["message"]
    assert res["action_required"] == "none"

def test_choose_storage_option_non_nfs_with_pv_success():
    res = choose_storage_option(storage_class="gp2", has_existing_pv=True, existing_pv_name="my-pv", storage_size="10Gi")
    assert res["pvc_needed"] is True
    assert res["existing_pv_name"] == "my-pv"
    assert "statically bound to your existing" in res["message"]
    assert res["action_required"] == "none"

def test_choose_storage_option_non_nfs_with_pv_missing_name():
    res = choose_storage_option(storage_class="gp2", has_existing_pv=True, existing_pv_name=None)
    assert res["pvc_needed"] is False
    assert res["action_required"] == "ask_pv_name"
    assert "provide the exact name" in res["message"]

def test_choose_storage_option_non_nfs_no_pv():
    res = choose_storage_option(storage_class="gp2", has_existing_pv=False, storage_size="5Gi")
    assert res["pvc_needed"] is True
    assert res["action_required"] == "confirm_dynamic_provisioning"
    assert "If your Kubernetes cluster support dynamic" in res["message"]

def test_deploy_app_success():
    res = deploy_app(
        app_name="web-app",
        image="nginx:alpine",
        container_port=80,
        replicas=2,
        namespace="web-ns",
        use_persistence=False,
        env_vars={"ENV": "prod"}
    )
    assert res["validation_status"] == "valid"
    assert "web-app" in res["manifests"]
    assert "web-ns" in res["manifests"]

def test_deploy_app_allowed_namespaces_failure():
    with patch("src.tools.config") as mock_config:
        mock_config.allowed_namespaces = ["prod", "dev"]
        mock_config.default_replicas = 1
        with pytest.raises(ValueError, match="not in the allowed list"):
            deploy_app(app_name="app", image="nginx", container_port=80, namespace="staging")

@patch("src.tools.k8s")
def test_plan_deployment_connected_success(mock_k8s):
    mock_k8s.check_connection.return_value = (True, "Connected")
    mock_k8s.apply_manifests.return_value = [
        {"kind": "Namespace", "name": "default", "status": "Created (dry-run)"},
        {"kind": "Deployment", "name": "test-app", "status": "Created (dry-run)"}
    ]
    
    res = plan_deployment(app_name="test-app", image="nginx", container_port=80)
    assert res["connected_to_cluster"] is True
    assert len(res["dry_run_results"]) == 2
    assert res["dry_run_results"][0]["status"] == "Created (dry-run)"
    assert res["review_required"] is True

@patch("src.tools.k8s")
def test_plan_deployment_disconnected(mock_k8s):
    mock_k8s.check_connection.return_value = (False, "Connection Refused")
    
    res = plan_deployment(app_name="test-app", image="nginx", container_port=80)
    assert res["connected_to_cluster"] is False
    assert "could not connect to cluster" in res["message"]
    assert res["dry_run_results"] == []

def test_apply_deployment_not_approved():
    with pytest.raises(ValueError, match="must be explicitly approved"):
        apply_deployment(manifests="apiVersion: v1\nkind: Namespace\nmetadata:\n  name: ns", approved=False)

@patch("src.tools.k8s")
def test_apply_deployment_success(mock_k8s):
    mock_k8s.check_connection.return_value = (True, "Connected")
    mock_k8s.apply_manifests.return_value = [
        {"kind": "Namespace", "name": "default", "status": "Created"}
    ]
    
    manifests = "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: default"
    res = apply_deployment(manifests=manifests, approved=True)
    assert res["status"] == "success"
    assert len(res["apply_results"]) == 1
    assert res["apply_results"][0]["status"] == "Created"

@patch("src.tools.k8s")
def test_create_namespace_success(mock_k8s):
    mock_k8s.check_connection.return_value = (True, "Connected")
    mock_k8s.create_namespace.return_value = "Namespace 'new-ns' successfully created."
    
    res = create_namespace(namespace="new-ns", dry_run=False)
    assert res["status"] == "success"
    assert "successfully created" in res["message"]

def test_get_service_endpoint():
    res = get_service_endpoint(app_name="web", namespace="dev", container_port=8080)
    assert res["service_name"] == "web"
    assert res["namespace"] == "dev"
    assert res["port"] == 8080
    assert res["dns_name"] == "web.dev.svc.cluster.local"
    assert res["endpoint"] == "http://web.dev.svc.cluster.local:8080"

def test_build_cloudflared_target():
    res = build_cloudflared_target(app_name="web", namespace="dev", container_port=8080)
    assert res["target"] == "http://web.dev.svc.cluster.local:8080"
