import os
import logging
from typing import List, Optional
import yaml

# Configure logging configuration initially
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mcp-k8s.config")

class ServerConfig:
    def __init__(self):
        # Default configuration values
        self.log_level: str = "INFO"
        self.kubeconfig_path: Optional[str] = None
        self.default_nfs_storage_class: str = "nfs"
        self.allowed_namespaces: List[str] = []
        self.default_replicas: int = 1
        self.default_container_port: int = 80
        self.default_storage_size: str = "10Gi"
        
        # Load from file first, then environment overrides
        self.load_from_yaml()
        self.load_from_env()
        
        # Apply configurations to python logging level
        self._apply_logging()

    def load_from_yaml(self):
        config_paths = [
            "config.yaml",
            "/etc/mcp-k8s/config.yaml"
        ]
        
        config_data = {}
        loaded_path = None
        for path in config_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        config_data = yaml.safe_load(f) or {}
                        loaded_path = path
                        break
                except Exception as e:
                    logger.warning(f"Failed to read config file {path}: {e}")
                    
        if loaded_path:
            logger.info(f"Loaded configuration from {loaded_path}")
            
            # Map YAML fields to settings
            if "logging" in config_data:
                self.log_level = config_data["logging"].get("level", self.log_level)
            
            if "kubernetes" in config_data:
                k8s = config_data["kubernetes"]
                self.kubeconfig_path = k8s.get("kubeconfig_path", self.kubeconfig_path) or None
                self.default_nfs_storage_class = k8s.get("default_nfs_storage_class", self.default_nfs_storage_class)
                self.allowed_namespaces = k8s.get("allowed_namespaces", self.allowed_namespaces) or []
                
            if "defaults" in config_data:
                defaults = config_data["defaults"]
                self.default_replicas = defaults.get("replicas", self.default_replicas)
                self.default_container_port = defaults.get("container_port", self.default_container_port)
                self.default_storage_size = defaults.get("storage_size", self.default_storage_size)

    def load_from_env(self):
        # Override with env vars if present
        self.log_level = os.getenv("MCP_K8S_LOG_LEVEL", self.log_level)
        self.default_nfs_storage_class = os.getenv("MCP_K8S_DEFAULT_NFS_STORAGE_CLASS", self.default_nfs_storage_class)
        
        kubeconfig = os.getenv("KUBECONFIG", os.getenv("MCP_K8S_KUBECONFIG_PATH"))
        if kubeconfig:
            self.kubeconfig_path = kubeconfig
            
        allowed_ns_str = os.getenv("MCP_K8S_ALLOWED_NAMESPACES")
        if allowed_ns_str is not None:
            if allowed_ns_str.strip() == "":
                self.allowed_namespaces = []
            else:
                self.allowed_namespaces = [ns.strip() for ns in allowed_ns_str.split(",") if ns.strip()]
                
        # Parse integers and fallback defaults safely
        if os.getenv("MCP_K8S_DEFAULT_REPLICAS"):
            try:
                self.default_replicas = int(os.getenv("MCP_K8S_DEFAULT_REPLICAS"))
            except ValueError:
                pass
                
        if os.getenv("MCP_K8S_DEFAULT_PORT"):
            try:
                self.default_container_port = int(os.getenv("MCP_K8S_DEFAULT_PORT"))
            except ValueError:
                pass
                
        self.default_storage_size = os.getenv("MCP_K8S_DEFAULT_STORAGE_SIZE", self.default_storage_size)

    def _apply_logging(self):
        level = getattr(logging, self.log_level.upper(), logging.INFO)
        logging.getLogger().setLevel(level)
        logger.setLevel(level)
        logger.info(f"Logging level configured to: {self.log_level.upper()}")

# Singleton instance of config
config = ServerConfig()
