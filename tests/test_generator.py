import yaml
from src.generator import (
    generate_namespace,
    generate_service,
    generate_pvc,
    generate_deployment,
    generate_manifests
)

def test_generate_namespace():
    ns = "test-namespace"
    manifest = generate_namespace(ns)
    assert manifest["apiVersion"] == "v1"
    assert manifest["kind"] == "Namespace"
    assert manifest["metadata"]["name"] == ns

def test_generate_service():
    name = "web"
    ns = "app-ns"
    port = 8080
    manifest = generate_service(name, ns, port)
    assert manifest["apiVersion"] == "v1"
    assert manifest["kind"] == "Service"
    assert manifest["metadata"]["name"] == name
    assert manifest["metadata"]["namespace"] == ns
    assert manifest["spec"]["type"] == "ClusterIP"
    assert manifest["spec"]["ports"][0]["port"] == port
    assert manifest["spec"]["selector"]["app"] == name

def test_generate_pvc_nfs():
    name = "app"
    ns = "default"
    storage_class = "nfs"  # default NFS class
    storage_size = "5Gi"
    
    # default config default_nfs_storage_class is 'nfs'
    manifest = generate_pvc(name, ns, storage_class, storage_size)
    assert manifest["apiVersion"] == "v1"
    assert manifest["kind"] == "PersistentVolumeClaim"
    assert manifest["metadata"]["name"] == f"{name}-pvc"
    assert manifest["spec"]["accessModes"] == ["ReadWriteMany"]
    assert manifest["spec"]["storageClassName"] == storage_class
    assert manifest["spec"]["resources"]["requests"]["storage"] == storage_size
    assert "volumeName" not in manifest["spec"]

def test_generate_pvc_with_pv():
    name = "app"
    ns = "default"
    storage_class = "gp2"
    storage_size = "10Gi"
    pv_name = "pv-12345"
    
    manifest = generate_pvc(name, ns, storage_class, storage_size, pv_name)
    assert manifest["spec"]["accessModes"] == ["ReadWriteOnce"]
    assert manifest["spec"]["volumeName"] == pv_name

def test_generate_deployment_no_persistence():
    name = "app"
    ns = "default"
    image = "nginx:alpine"
    port = 80
    replicas = 2
    env_vars = {"B_KEY": "2", "A_KEY": "1"}
    
    manifest = generate_deployment(name, ns, image, port, replicas, env_vars, use_persistence=False)
    assert manifest["apiVersion"] == "apps/v1"
    assert manifest["kind"] == "Deployment"
    assert manifest["metadata"]["name"] == name
    assert manifest["spec"]["replicas"] == replicas
    
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == image
    assert container["ports"][0]["containerPort"] == port
    
    # Check that environment variables are sorted
    assert container["env"] == [
        {"name": "A_KEY", "value": "1"},
        {"name": "B_KEY", "value": "2"}
    ]
    
    # Verify security context
    assert container["securityContext"]["runAsNonRoot"] is True
    assert "volumeMounts" not in container
    assert "volumes" not in manifest["spec"]["template"]["spec"]

def test_generate_deployment_with_persistence():
    name = "app"
    ns = "default"
    image = "nginx"
    port = 80
    replicas = 1
    
    manifest = generate_deployment(name, ns, image, port, replicas, use_persistence=True)
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    
    assert container["volumeMounts"][0]["name"] == "app-data"
    assert container["volumeMounts"][0]["mountPath"] == "/data"
    
    volumes = manifest["spec"]["template"]["spec"]["volumes"]
    assert volumes[0]["name"] == "app-data"
    assert volumes[0]["persistentVolumeClaim"]["claimName"] == f"{name}-pvc"

def test_generate_manifests_integration():
    inputs = {
        "app_name": "my-cool-app",
        "image": "redis:alpine",
        "container_port": 6379,
        "replicas": 1,
        "namespace": "database",
        "use_persistence": True,
        "storage_class": "local-path",
        "storage_size": "2Gi",
        "env_vars": {"REDIS_PASSWORD": "pass"}
    }
    
    yaml_str = generate_manifests(inputs)
    resources = list(yaml.safe_load_all(yaml_str))
    
    # Should contain: Namespace, PVC, Deployment, Service
    assert len(resources) == 4
    kinds = [r["kind"] for r in resources]
    assert kinds == ["Namespace", "PersistentVolumeClaim", "Deployment", "Service"]
    
    assert resources[0]["metadata"]["name"] == "database"
    assert resources[1]["metadata"]["name"] == "my-cool-app-pvc"
    assert resources[2]["metadata"]["name"] == "my-cool-app"
    assert resources[3]["metadata"]["name"] == "my-cool-app"
