from typing import Dict, List, Optional
import yaml
from src.config import config

def generate_namespace(namespace: str) -> dict:
    """Generates a Kubernetes Namespace manifest."""
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": namespace,
            "labels": {
                "managed-by": "mcp-k8s-deployer"
            }
        }
    }

def generate_service(app_name: str, namespace: str, container_port: int) -> dict:
    """Generates a Kubernetes Service manifest exposing the app."""
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": app_name,
            "namespace": namespace,
            "labels": {
                "app": app_name,
                "managed-by": "mcp-k8s-deployer"
            }
        },
        "spec": {
            "type": "ClusterIP",
            "selector": {
                "app": app_name
            },
            "ports": [
                {
                    "name": "http",
                    "protocol": "TCP",
                    "port": container_port,
                    "targetPort": container_port
                }
            ]
        }
    }

def generate_pvc(
    app_name: str, 
    namespace: str, 
    storage_class: str, 
    storage_size: str, 
    existing_pv_name: Optional[str] = None
) -> dict:
    """Generates a Kubernetes PersistentVolumeClaim manifest."""
    pvc_spec: dict = {
        "accessModes": [
            "ReadWriteMany" if storage_class == config.default_nfs_storage_class else "ReadWriteOnce"
        ],
        "storageClassName": storage_class,
        "resources": {
            "requests": {
                "storage": storage_size
            }
        }
    }
    
    if existing_pv_name:
        pvc_spec["volumeName"] = existing_pv_name
        
    return {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": f"{app_name}-pvc",
            "namespace": namespace,
            "labels": {
                "app": app_name,
                "managed-by": "mcp-k8s-deployer"
            }
        },
        "spec": pvc_spec
    }

def generate_deployment(
    app_name: str,
    namespace: str,
    image: str,
    container_port: int,
    replicas: int,
    env_vars: Optional[Dict[str, str]] = None,
    use_persistence: bool = False
) -> dict:
    """Generates a Kubernetes Deployment manifest."""
    container: dict = {
        "name": app_name,
        "image": image,
        "ports": [
            {
                "name": "http",
                "containerPort": container_port
            }
        ],
        "resources": {
            "limits": {
                "cpu": "500m",
                "memory": "512Mi"
            },
            "requests": {
                "cpu": "100m",
                "memory": "128Mi"
            }
        }
    }
    
    # Secure defaults
    container["securityContext"] = {
        "allowPrivilegeEscalation": False,
        "capabilities": {
            "drop": ["ALL"]
        },
        "runAsNonRoot": True,
        "runAsUser": 1000,
        "readOnlyRootFilesystem": False  # Allow writes if needed, but restrict permissions
    }
    
    # Process Environment Variables (sorted for deterministic tests)
    if env_vars:
        container["env"] = [
            {"name": k, "value": str(v)}
            for k, v in sorted(env_vars.items())
        ]
        
    pod_spec: dict = {
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 1000,
            "fsGroup": 2000
        },
        "containers": [container]
    }
    
    # Persistence volume configuration
    if use_persistence:
        container["volumeMounts"] = [
            {
                "name": "app-data",
                "mountPath": "/data"
            }
        ]
        pod_spec["volumes"] = [
            {
                "name": "app-data",
                "persistentVolumeClaim": {
                    "claimName": f"{app_name}-pvc"
                }
            }
        ]
        
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": app_name,
            "namespace": namespace,
            "labels": {
                "app": app_name,
                "managed-by": "mcp-k8s-deployer"
            }
        },
        "spec": {
            "replicas": replicas,
            "selector": {
                "matchLabels": {
                    "app": app_name
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": app_name
                    }
                },
                "spec": pod_spec
            }
        }
    }

def generate_manifests(inputs: dict) -> str:
    """
    Combines input fields to produce a multi-document YAML manifest string.
    Inputs dictionary must have been validated already.
    """
    app_name = inputs["app_name"]
    namespace = inputs["namespace"]
    image = inputs["image"]
    container_port = inputs["container_port"]
    replicas = inputs.get("replicas", config.default_replicas)
    env_vars = inputs.get("env_vars")
    use_persistence = inputs.get("use_persistence", False)
    
    manifests = []
    
    # 1. Namespace
    manifests.append(generate_namespace(namespace))
    
    # 2. Persistent Volume Claim (if needed)
    if use_persistence:
        storage_class = inputs.get("storage_class") or config.default_nfs_storage_class
        storage_size = inputs.get("storage_size") or config.default_storage_size
        existing_pv_name = inputs.get("existing_pv_name")
        manifests.append(generate_pvc(app_name, namespace, storage_class, storage_size, existing_pv_name))
        
    # 3. Deployment
    manifests.append(generate_deployment(
        app_name=app_name,
        namespace=namespace,
        image=image,
        container_port=container_port,
        replicas=replicas,
        env_vars=env_vars,
        use_persistence=use_persistence
    ))
    
    # 4. Service
    manifests.append(generate_service(app_name, namespace, container_port))
    
    # Serialize to multi-document YAML
    return yaml.safe_dump_all(manifests, default_flow_style=False, sort_keys=False)
