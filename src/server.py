import logging
from typing import Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from src.tools import (
    choose_storage_option,
    deploy_app,
    plan_deployment,
    apply_deployment,
    create_namespace,
    get_service_endpoint,
    build_cloudflared_target
)

# Initialize logging
logger = logging.getLogger("mcp-k8s.server")

# Initialize FastMCP Server
mcp = FastMCP("kubernetes-deployer")

@mcp.tool()
def choose_storage_option_tool(
    storage_class: str,
    has_existing_pv: bool,
    existing_pv_name: Optional[str] = None,
    storage_size: Optional[str] = None,
    default_nfs_class: Optional[str] = None
) -> dict:
    """
    Assesses persistent storage options based on StorageClass and PV presence.
    Helps determine PV binding versus new PVC creation.

    Args:
        storage_class: The StorageClass requested (e.g. 'nfs', 'local-path', 'standard').
        has_existing_pv: Set to True if an existing PersistentVolume (PV) is available.
        existing_pv_name: The name of the existing PersistentVolume (PV), if available.
        storage_size: The desired storage size (e.g., '10Gi', '1Gi').
        default_nfs_class: Override default NFS StorageClass configuration.
    """
    return choose_storage_option(
        storage_class=storage_class,
        has_existing_pv=has_existing_pv,
        existing_pv_name=existing_pv_name,
        storage_size=storage_size,
        default_nfs_class=default_nfs_class
    )

@mcp.tool()
def deploy_app_tool(
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
    """
    Collects application configuration and generates Kubernetes manifests.

    Args:
        app_name: Unique name for the application (DNS-compliant).
        image: Container image path (e.g., 'nginx:alpine').
        container_port: Network port the container listens on (1-65535).
        replicas: Number of Pod replicas (default: 1).
        namespace: Target Kubernetes namespace (default: 'default').
        use_persistence: Set to True if the app requires persistent storage.
        storage_class: StorageClass to use for persistent storage.
        storage_size: Storage size requested (e.g. '10Gi').
        existing_pv_name: Name of an existing PersistentVolume (PV) to bind to.
        env_vars: Dictionary of environment variables for the container.
        hostname: Optional hostname for cloudflared public route mapping.
    """
    return deploy_app(
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

@mcp.tool()
def plan_deployment_tool(
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
    """
    Validates configuration, generates manifests, and dry-runs against the cluster.
    Shows the exact resources that would be created or modified.

    Args:
        app_name: Unique name for the application (DNS-compliant).
        image: Container image path (e.g., 'nginx:alpine').
        container_port: Network port the container listens on (1-65535).
        replicas: Number of Pod replicas (default: 1).
        namespace: Target Kubernetes namespace (default: 'default').
        use_persistence: Set to True if the app requires persistent storage.
        storage_class: StorageClass to use for persistent storage.
        storage_size: Storage size requested (e.g. '10Gi').
        existing_pv_name: Name of an existing PersistentVolume (PV) to bind to.
        env_vars: Dictionary of environment variables for the container.
        hostname: Optional hostname for cloudflared public route mapping.
    """
    return plan_deployment(
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

@mcp.tool()
def apply_deployment_tool(
    manifests: str,
    approved: bool = False
) -> dict:
    """
    Applies the generated and approved Kubernetes manifests to the cluster.

    Args:
        manifests: Multi-document YAML string containing the Kubernetes resources.
        approved: Must be set to True. Enforces user review before applying configuration.
    """
    return apply_deployment(
        manifests=manifests,
        approved=approved
    )

@mcp.tool()
def create_namespace_tool(
    namespace: str,
    dry_run: bool = False
) -> dict:
    """
    Creates a new namespace if it doesn't already exist.

    Args:
        namespace: The namespace name to create (DNS-compliant).
        dry_run: If True, performs a dry-run check without creating it.
    """
    return create_namespace(
        namespace=namespace,
        dry_run=dry_run
    )

@mcp.tool()
def get_service_endpoint_tool(
    app_name: str,
    namespace: str,
    container_port: int
) -> dict:
    """
    Returns the internal cluster DNS name and port for the service.

    Args:
        app_name: The application/service name.
        namespace: The namespace where the service resides.
        container_port: The container port exposed.
    """
    return get_service_endpoint(
        app_name=app_name,
        namespace=namespace,
        container_port=container_port
    )

@mcp.tool()
def build_cloudflared_target_tool(
    app_name: str,
    namespace: str,
    container_port: int
) -> dict:
    """
    Generates the exact target service string suitable for cloudflared config.

    Args:
        app_name: The application/service name.
        namespace: The namespace where the service resides.
        container_port: The service port.
    """
    return build_cloudflared_target(
        app_name=app_name,
        namespace=namespace,
        container_port=container_port
    )

def main():
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Kubernetes App Deployment Orchestration MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport protocol to use (default: stdio)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind for SSE transport (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind for SSE transport (default: 8000)"
    )
    args = parser.parse_args()

    # Support environment variable overrides
    transport = os.getenv("MCP_TRANSPORT", args.transport)
    host = os.getenv("MCP_HOST", args.host)
    
    port_env = os.getenv("MCP_PORT")
    port = int(port_env) if port_env else args.port

    if transport == "sse":
        logger.info(f"Starting Kubernetes MCP server over SSE transport on {host}:{port}...")
        mcp.run(transport="sse", host=host, port=port)
    else:
        logger.info("Starting Kubernetes MCP server over Stdio transport...")
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
