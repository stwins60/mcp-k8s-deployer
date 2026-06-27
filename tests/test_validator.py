import pytest
from src.validator import validate_app_inputs, validate_manifests_yaml

def test_validate_app_inputs_success():
    valid_inputs = {
        "app_name": "my-app",
        "image": "nginx:latest",
        "container_port": 80,
        "replicas": 3,
        "namespace": "production",
        "use_persistence": True,
        "storage_class": "standard",
        "storage_size": "10Gi",
        "existing_pv_name": "my-pv",
        "env_vars": {"ENV_VAR": "value"},
        "hostname": "app.example.com"
    }
    validated = validate_app_inputs(valid_inputs)
    assert validated["app_name"] == "my-app"
    assert validated["replicas"] == 3
    assert validated["container_port"] == 80
    assert validated["storage_size"] == "10Gi"
    assert validated["hostname"] == "app.example.com"

def test_validate_app_inputs_minimal():
    minimal_inputs = {
        "app_name": "web",
        "image": "nginx",
        "container_port": 8080,
        "namespace": "default"
    }
    validated = validate_app_inputs(minimal_inputs)
    assert validated["app_name"] == "web"
    assert validated["replicas"] == 1  # Default value
    assert validated["use_persistence"] is False

def test_validate_app_inputs_invalid_names():
    invalid_inputs = {
        "app_name": "My_App",  # Capital letters and underscores invalid in DNS Label
        "image": "nginx",
        "container_port": 80,
        "namespace": "default"
    }
    with pytest.raises(ValueError, match="Must be a valid DNS subdomain label"):
        validate_app_inputs(invalid_inputs)

def test_validate_app_inputs_invalid_port():
    invalid_inputs = {
        "app_name": "app",
        "image": "nginx",
        "container_port": 99999,  # Port too large
        "namespace": "default"
    }
    with pytest.raises(ValueError, match="container_port"):
        validate_app_inputs(invalid_inputs)

def test_validate_app_inputs_invalid_storage_size():
    invalid_inputs = {
        "app_name": "app",
        "image": "nginx",
        "container_port": 80,
        "namespace": "default",
        "use_persistence": True,
        "storage_size": "10GB"  # GB is not valid in K8s (Gi, G, M, Mi are)
    }
    with pytest.raises(ValueError, match="Must be a valid Kubernetes quantity"):
        validate_app_inputs(invalid_inputs)

def test_validate_manifests_yaml_success():
    valid_yaml = """
apiVersion: v1
kind: Namespace
metadata:
  name: my-namespace
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: my-namespace
spec:
  replicas: 1
"""
    resources = validate_manifests_yaml(valid_yaml)
    assert len(resources) == 2
    assert resources[0]["kind"] == "Namespace"
    assert resources[1]["kind"] == "Deployment"

def test_validate_manifests_yaml_invalid_missing_fields():
    invalid_yaml = """
apiVersion: v1
# missing kind
metadata:
  name: my-namespace
"""
    with pytest.raises(ValueError, match="missing required field 'kind'"):
        validate_manifests_yaml(invalid_yaml)

def test_validate_manifests_yaml_invalid_syntax():
    invalid_yaml = """
apiVersion: v1
kind: [unclosed bracket
"""
    with pytest.raises(ValueError, match="Failed to parse YAML manifest"):
        validate_manifests_yaml(invalid_yaml)
