import logging
from typing import Dict, List, Optional
from src.config import config
from src.validator import validate_app_inputs, validate_manifests_yaml
from src.generator import generate_manifests
from src.k8s_client import k8s

logger = logging.getLogger("mcp-k8s.tools")

def choose_storage_option(
    storage_class: str,
    has_existing_pv: bool,
    existing_pv_name: Optional[str] = None,
    storage_size: Optional[str] = None,
    default_nfs_class: Optional[str] = None
) -> dict:
    """
    Assesses persistent storage options based on StorageClass and PV presence.
    Helps guide the client/user on whether to create a PVC, bind to an existing PV, or ask for more details.
    """
    nfs_class = default_nfs_class or config.default_nfs_storage_class
    size = storage_size or config.default_storage_size
    
    # 1. NFS storage class logic
    if storage_class == nfs_class:
        return {
            "use_persistence": True,
            "storage_class": storage_class,
            "storage_size": size,
            "existing_pv_name": None,
            "pvc_needed": True,
            "action_required": "none",
            "message": f"StorageClass '{storage_class}' matches the default NFS configuration. "
                       f"A PersistentVolumeClaim (PVC) of size {size} will be dynamically created. "
                       f"No existing PersistentVolume (PV) is required since NFS handles dynamic provisioning."
        }
        
    # 2. Non-NFS StorageClass logic
    if has_existing_pv:
        if not existing_pv_name:
            return {
                "use_persistence": True,
                "storage_class": storage_class,
                "storage_size": size,
                "existing_pv_name": None,
                "pvc_needed": False,
                "action_required": "ask_pv_name",
                "message": f"StorageClass '{storage_class}' is different from the default NFS class. "
                           f"You specified that an existing PV is available, but did not provide 'existing_pv_name'. "
                           f"Please prompt the user to provide the exact name of the existing PersistentVolume (PV)."
            }
        else:
            return {
                "use_persistence": True,
                "storage_class": storage_class,
                "storage_size": size,
                "existing_pv_name": existing_pv_name,
                "pvc_needed": True,
                "action_required": "none",
                "message": f"StorageClass '{storage_class}' is a non-default class. "
                           f"A PVC of size {size} will be generated and statically bound to your "
                           f"existing PersistentVolume '{existing_pv_name}'."
            }
            
    # 3. Non-NFS, no existing PV
    return {
        "use_persistence": True,
        "storage_class": storage_class,
        "storage_size": size,
        "existing_pv_name": None,
        "pvc_needed": True,
        "action_required": "confirm_dynamic_provisioning",
        "message": f"StorageClass '{storage_class}' is different from the default NFS class. "
                   f"A new PVC of size {size} will be created. If your Kubernetes cluster support dynamic "
                   f"provisioning for StorageClass '{storage_class}', the PV will be automatically created. "
                   f"If dynamic provisioning is not supported, the pod will fail to bind unless an existing "
                   f"PV is provided. Please confirm if dynamic provisioning is available, or if a PV already exists."
    }

def deploy_app(
    app_name: str,
    image: str,
    container_port: int,
    replicas: int = 1,
    namespace: str = "default",
    use_persistence: bool = False,
    storage_class: Optional[str] = None,
    storage_size: Optional[str] = None,
    existing_pv_name: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None,
    hostname: Optional[str] = None
) -> dict:
    """Collects inputs, validates them, and generates Kubernetes manifests."""
    # Ensure allowed namespace checks
    if config.allowed_namespaces and namespace not in config.allowed_namespaces:
        raise ValueError(
            f"Namespace '{namespace}' is not in the allowed list: {config.allowed_namespaces}"
        )

    # Validate inputs
    inputs = {
        "app_name": app_name,
        "image": image,
        "container_port": container_port,
        "replicas": replicas,
        "namespace": namespace,
        "use_persistence": use_persistence,
        "storage_class": storage_class,
        "storage_size": storage_size,
        "existing_pv_name": existing_pv_name,
        "env_vars": env_vars,
        "hostname": hostname
    }
    validated_inputs = validate_app_inputs(inputs)
    
    # Generate manifests
    manifests = generate_manifests(validated_inputs)
    
    # Run YAML parsing check as secondary validation
    validate_manifests_yaml(manifests)
    
    return {
        "manifests": manifests,
        "validation_status": "valid",
        "message": f"Successfully generated manifests for '{app_name}' in namespace '{namespace}'."
    }

def plan_deployment(
    app_name: str,
    image: str,
    container_port: int,
    replicas: int = 1,
    namespace: str = "default",
    use_persistence: bool = False,
    storage_class: Optional[str] = None,
    storage_size: Optional[str] = None,
    existing_pv_name: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None,
    hostname: Optional[str] = None
) -> dict:
    """Validates inputs, generates manifests, and runs a cluster dry-run to show planned actions."""
    # Generate manifests first
    deploy_res = deploy_app(
        app_name=app_name,
        image=image,
        container_port=container_port,
        replicas=replicas,
        namespace=namespace,
        use_persistence=use_persistence,
        storage_class=storage_class,
        storage_size=storage_size,
        existing_pv_name=existing_pv_name,
        env_vars=env_vars,
        hostname=hostname
    )
    
    manifests = deploy_res["manifests"]
    
    # Check cluster connection
    connected, conn_msg = k8s.check_connection()
    if not connected:
        return {
            "manifests": manifests,
            "dry_run_results": [],
            "message": f"Manifests generated successfully, but could not connect to cluster for planning: {conn_msg}. "
                       f"Please check your Kubernetes cluster settings.",
            "review_required": True,
            "connected_to_cluster": False
        }
        
    # Execute dry-run apply
    try:
        dry_run_results = k8s.apply_manifests(manifests, dry_run=True)
        return {
            "manifests": manifests,
            "dry_run_results": dry_run_results,
            "message": f"Successfully planned deployment for '{app_name}'. Manifests validated and dry-run applied successfully.",
            "review_required": True,
            "connected_to_cluster": True
        }
    except Exception as e:
        logger.error(f"Dry-run plan failed: {e}")
        return {
            "manifests": manifests,
            "dry_run_results": [],
            "message": f"Manifest generation succeeded, but dry-run apply against the cluster failed: {str(e)}",
            "review_required": True,
            "connected_to_cluster": True,
            "error": str(e)
        }

def apply_deployment(manifests: str, approved: bool = False) -> dict:
    """Applies the approved manifests to the cluster."""
    if not approved:
        raise ValueError(
            "Deployment must be explicitly approved. Call plan_deployment first, "
            "present the changes to the user, and set 'approved=True' to apply."
        )
        
    # Validate YAML schema first
    validate_manifests_yaml(manifests)
    
    # Check cluster connection
    connected, conn_msg = k8s.check_connection()
    if not connected:
        raise RuntimeError(f"Cannot apply deployment: {conn_msg}")
        
    try:
        apply_results = k8s.apply_manifests(manifests, dry_run=False)
        return {
            "apply_results": apply_results,
            "message": "Successfully applied manifests to the Kubernetes cluster.",
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Failed to apply deployment manifests: {e}")
        raise RuntimeError(f"Failed to apply deployment manifests: {str(e)}")

def create_namespace(namespace: str, dry_run: bool = False) -> dict:
    """Creates a namespace if requested and verified."""
    if config.allowed_namespaces and namespace not in config.allowed_namespaces:
        raise ValueError(
            f"Namespace '{namespace}' is not in the allowed list: {config.allowed_namespaces}"
        )
        
    connected, conn_msg = k8s.check_connection()
    if not connected:
        raise RuntimeError(f"Cannot create namespace: {conn_msg}")
        
    try:
        status_msg = k8s.create_namespace(namespace, dry_run=dry_run)
        return {
            "namespace": namespace,
            "dry_run": dry_run,
            "message": status_msg,
            "status": "success"
        }
    except Exception as e:
        raise RuntimeError(f"Failed to create namespace '{namespace}': {str(e)}")

def get_service_endpoint(app_name: str, namespace: str, container_port: int) -> dict:
    """Returns the internal cluster Service DNS endpoint."""
    dns_name = f"{app_name}.{namespace}.svc.cluster.local"
    return {
        "service_name": app_name,
        "namespace": namespace,
        "port": container_port,
        "dns_name": dns_name,
        "endpoint": f"http://{dns_name}:{container_port}",
        "message": f"Internal DNS: http://{dns_name}:{container_port}"
    }

def build_cloudflared_target(app_name: str, namespace: str, container_port: int) -> dict:
    """Returns the exact service target to use when configuring cloudflared."""
    dns_name = f"{app_name}.{namespace}.svc.cluster.local"
    target_url = f"http://{dns_name}:{container_port}"
    return {
        "target": target_url,
        "message": f"Use the target URL '{target_url}' to route public traffic to this app via cloudflared."
    }
