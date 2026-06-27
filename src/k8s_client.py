import logging
import yaml
from typing import Dict, List, Optional, Tuple
from kubernetes import client, config, dynamic
from kubernetes.client.exceptions import ApiException
from src.config import config as server_config

logger = logging.getLogger("mcp-k8s.k8s_client")

class K8sClient:
    def __init__(self):
        self._initialized = False
        self.api_client = None
        self.dyn_client = None
        self.core_v1 = None
        
        self.initialize_client()

    def initialize_client(self):
        try:
            if server_config.kubeconfig_path:
                config.load_kube_config(config_file=server_config.kubeconfig_path)
                logger.info(f"Loaded kubeconfig from {server_config.kubeconfig_path}")
            else:
                try:
                    config.load_kube_config()
                    logger.info("Loaded default system kubeconfig")
                except Exception:
                    # Fallback to in-cluster config
                    config.load_incluster_config()
                    logger.info("Loaded in-cluster Kubernetes configuration")
                    
            self.api_client = client.ApiClient()
            self.dyn_client = dynamic.DynamicClient(self.api_client)
            self.core_v1 = client.CoreV1Api(self.api_client)
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes client: {e}")
            self._initialized = False

    def check_connection(self) -> Tuple[bool, str]:
        """Verifies connection to the cluster by listing namespaces."""
        if not self._initialized:
            return False, "Kubernetes client not initialized. Check configuration and cluster status."
        try:
            self.core_v1.list_namespace(limit=1)
            return True, "Successfully connected to the Kubernetes cluster"
        except Exception as e:
            return False, f"Failed to connect to cluster: {str(e)}"

    def namespace_exists(self, namespace: str) -> bool:
        """Checks if a namespace exists in the cluster."""
        if not self._initialized:
            raise RuntimeError("Kubernetes client is not initialized")
        try:
            self.core_v1.read_namespace(name=namespace)
            return True
        except ApiException as e:
            if e.status == 404:
                return False
            raise e

    def create_namespace(self, namespace: str, dry_run: bool = False) -> str:
        """Creates a namespace if it does not already exist."""
        if not self._initialized:
            raise RuntimeError("Kubernetes client is not initialized")
        
        if self.namespace_exists(namespace):
            return f"Namespace '{namespace}' already exists."

        body = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": namespace,
                "labels": {
                    "managed-by": "mcp-k8s-deployer"
                }
            }
        }
        
        try:
            kwargs = {"body": body}
            if dry_run:
                kwargs["dry_run"] = "All"
                
            self.core_v1.create_namespace(**kwargs)
            action = "planned (dry-run)" if dry_run else "created"
            logger.info(f"Namespace '{namespace}' {action}")
            return f"Namespace '{namespace}' successfully {action}."
        except ApiException as e:
            logger.error(f"Failed to create namespace '{namespace}': {e}")
            raise RuntimeError(f"Failed to create namespace '{namespace}': {e.reason}")

    def apply_resource(self, resource: dict, dry_run: bool = False, namespaces_in_manifests: Optional[set] = None) -> Dict[str, str]:
        """
        Creates or patches a single Kubernetes resource.
        Works like 'kubectl apply' by attempting a create and falling back to a patch if the resource exists.
        """
        if not self._initialized:
            raise RuntimeError("Kubernetes client is not initialized")

        api_version = resource.get("apiVersion")
        kind = resource.get("kind")
        metadata = resource.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace")

        if not api_version or not kind or not name:
            raise ValueError("Resource manifest is missing apiVersion, kind, or metadata.name")

        try:
            # Look up dynamic resource interface
            api = self.dyn_client.resources.get(api_version=api_version, kind=kind)
        except Exception as e:
            raise ValueError(f"Resource type {kind} ({api_version}) not supported by cluster: {e}")

        # Determine if resource is namespaced
        is_namespaced = api.namespaced
        
        # Prepare parameters
        create_kwargs = {"body": resource}
        if is_namespaced and namespace:
            create_kwargs["namespace"] = namespace
        if dry_run:
            create_kwargs["dry_run"] = "All"

        try:
            # Attempt to create
            logger.debug(f"Attempting to create {kind} '{name}' in namespace '{namespace}' (dry_run={dry_run})")
            api.create(**create_kwargs)
            action = "Created"
        except ApiException as e:
            if e.status == 409:  # Conflict / Already exists
                # Fallback to patch
                logger.debug(f"Resource {kind} '{name}' already exists. Patching (dry_run={dry_run})...")
                
                patch_kwargs = {
                    "name": name,
                    "body": resource,
                    "content_type": "application/merge-patch+json"
                }
                if is_namespaced and namespace:
                    patch_kwargs["namespace"] = namespace
                if dry_run:
                    patch_kwargs["dry_run"] = "All"
                
                try:
                    api.patch(**patch_kwargs)
                    action = "Patched"
                except ApiException as patch_err:
                    logger.error(f"Failed to patch {kind} '{name}': {patch_err}")
                    raise RuntimeError(f"Failed to patch {kind} '{name}': {patch_err.reason}")
            elif dry_run and e.status == 404 and namespaces_in_manifests and namespace in namespaces_in_manifests:
                # Catch namespace not found during dry-run when namespace is part of the manifests
                logger.info(f"Dry-run for namespaced resource {kind} '{name}' skipped because parent namespace '{namespace}' is not yet created.")
                action = "Planned (pending namespace creation)"
            else:
                logger.error(f"Failed to create {kind} '{name}': {e}")
                raise RuntimeError(f"Failed to create {kind} '{name}': {e.reason}")

        status_str = f"{action} (dry-run)" if dry_run and not action.startswith("Planned") else action
        logger.info(f"Resource {kind} '{name}' in namespace '{namespace or 'cluster-scope'}' status: {status_str}")
        return {
            "kind": kind,
            "name": name,
            "namespace": namespace or "",
            "status": status_str
        }

    def apply_manifests(self, yaml_str: str, dry_run: bool = False) -> List[Dict[str, str]]:
        """Parses multi-document YAML and applies each resource sequentially."""
        try:
            resources = list(yaml.safe_load_all(yaml_str))
        except Exception as e:
            raise ValueError(f"Failed to parse YAML manifest: {e}")

        # Extract all Namespace names being created in this manifest set
        namespaces_in_manifests = {
            r["metadata"]["name"] 
            for r in resources 
            if r and isinstance(r, dict) and r.get("kind") == "Namespace" and "metadata" in r and "name" in r["metadata"]
        }

        results = []
        for resource in resources:
            if resource is None:
                continue
            res = self.apply_resource(resource, dry_run=dry_run, namespaces_in_manifests=namespaces_in_manifests)
            results.append(res)
            
        return results

# Singleton instance
k8s = K8sClient()
