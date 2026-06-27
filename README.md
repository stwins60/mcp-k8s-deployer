# Kubernetes App Deployment Orchestration MCP Server

A production-ready Model Context Protocol (MCP) server that empowers LLMs to dynamically orchestrate containerized application deployments to a Kubernetes cluster. 

It handles configuration validation, interactive storage resolution, multi-resource manifest generation (Namespace, PersistentVolumeClaim, Deployment, Service), dry-run plan reviews, actual apply actions, and service endpoints extraction optimized for `cloudflared` tunnel routing.

---

## Architecture Overview

For a detailed view of the system design and interaction flow, see the approved [Implementation Plan](.gemini/antigravity-ide/brain/0128e6ba-36df-49fe-a865-64838e050951/implementation_plan.md).

![Architecture Diagram](.gemini/antigravity-ide/brain/0128e6ba-36df-49fe-a865-64838e050951/mcp_k8s_architecture_1782533118153.png)

---

## Features

- **Interactive Storage Resolution**: Dynamically checks whether to create a new PVC, bind to an existing PV, or prompt the user for more details depending on whether the StorageClass matches the cluster's default NFS setup.
- **Strict Input Validation**: Enforces RFC 1123 compliant naming for apps, namespaces, and StorageClasses, validates port ranges, replicas, image tags, and Kubernetes storage sizes (e.g. `10Gi`).
- **Dry-run Planning & Actual Applying**: Exposes separate planning (`plan_deployment`) and apply (`apply_deployment`) stages. Planning runs a Kubernetes server-side dry-run to catch configuration errors before changes are committed.
- **Enforced Review Step**: The `apply_deployment` tool requires an explicit `approved=True` parameter to enforce user verification of planned changes.
- **Tunnel Mapping Helpers**: Auto-formats endpoints to seamlessly configure public subdomains with `cloudflared` tunnels.

---

## Prerequisites

- **Python**: Version 3.10 or higher.
- **Kubernetes Cluster**: Access to a running cluster (e.g., k3s, minikube, GKE, EKS) with cluster credentials.
- **Credentials**: A valid kubeconfig file (defaults to `~/.kube/config`).

---

## Installation & Setup

1. **Clone or navigate to the workspace**:
   ```bash
   cd /home/prod-server-2/mcp-k8s-deployer
   ```

2. **Create a virtual environment and install dependencies**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Verify the installation by running the test suite**:
   ```bash
   python3 -m pytest -v
   ```

---

## Configuration

The server supports configuration through environment variables or a YAML configuration file.

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `MCP_K8S_LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `MCP_K8S_DEFAULT_NFS_STORAGE_CLASS` | StorageClass name treated as default NFS-backed storage | `nfs` |
| `MCP_K8S_ALLOWED_NAMESPACES` | Comma-separated list of allowed namespaces. If empty, all are allowed. | `""` |
| `KUBECONFIG` or `MCP_K8S_KUBECONFIG_PATH` | Path to the active cluster kubeconfig file | `~/.kube/config` |
| `MCP_K8S_DEFAULT_REPLICAS` | Default pod replicas count if unspecified | `1` |
| `MCP_K8S_DEFAULT_PORT` | Default service port if unspecified | `80` |
| `MCP_K8S_DEFAULT_STORAGE_SIZE` | Default persistent volume size | `10Gi` |

### YAML Configuration File

Create a `config.yaml` file in the root of the project (or store it in `/etc/mcp-k8s/config.yaml`). See [config.yaml.example](config.yaml.example) for template fields.

```yaml
logging:
  level: "INFO"
kubernetes:
  kubeconfig_path: ""  # Empty uses default ~/.kube/config
  default_nfs_storage_class: "nfs"
  allowed_namespaces: []
defaults:
  replicas: 1
  container_port: 80
  storage_size: "10Gi"
```

---

## Exposed MCP Tools

The server exposes the following tools to MCP-enabled clients:

### 1. `choose_storage_option_tool`
Assesses storage configuration based on StorageClass and PV requirements.
* **Arguments**:
  - `storage_class` (str, required): The target storage class name (e.g. `nfs`, `local-path`).
  - `has_existing_pv` (bool, required): Whether the user has an existing PersistentVolume (PV) created.
  - `existing_pv_name` (str, optional): The name of the existing PV to bind statically.
  - `storage_size` (str, optional): Desired disk size (e.g. `5Gi`).
  - `default_nfs_class` (str, optional): Override the default NFS storage class config.
* **Returns**: A JSON dictionary advising on PVC generation, PV binding, or actions required.

### 2. `deploy_app_tool`
Gathers configurations, validates inputs, and generates Kubernetes manifests in YAML format.
* **Arguments**:
  - `app_name` (str, required)
  - `image` (str, required)
  - `container_port` (int, required)
  - `replicas` (int, optional)
  - `namespace` (str, optional)
  - `use_persistence` (bool, optional)
  - `storage_class` (str, optional)
  - `storage_size` (str, optional)
  - `existing_pv_name` (str, optional)
  - `env_vars` (dict, optional)
  - `hostname` (str, optional)
* **Returns**: Generates a multi-document YAML string representing the Namespace, PVC, Deployment, and Service.

### 3. `plan_deployment_tool`
Validates inputs, generates manifests, and runs a **server-side dry-run apply** against the cluster. Shows the exact plan of actions.
* **Arguments**: Same as `deploy_app_tool`.
* **Returns**: The generated manifests, dry-run actions list (e.g., `Created`, `Patched`), and validation status.

### 4. `apply_deployment_tool`
Applies approved manifests to the Kubernetes cluster.
* **Arguments**:
  - `manifests` (str, required): The generated YAML manifests.
  - `approved` (bool, required): Enforces safety. Must be set to `True`.
* **Returns**: Success status and array of resources created or patched.

### 5. `create_namespace_tool`
Creates a namespace if requested and it doesn't already exist.
* **Arguments**:
  - `namespace` (str, required): The namespace to create.
  - `dry_run` (bool, optional): Runs dry-run check if `True`.

### 6. `get_service_endpoint_tool`
Computes the internal cluster Service DNS endpoint.
* **Arguments**: `app_name` (str), `namespace` (str), `container_port` (int).
* **Returns**: The service URL (e.g. `http://app.namespace.svc.cluster.local:80`).

### 7. `build_cloudflared_target_tool`
Generates the exact target service string to paste into a cloudflared tunnel mapping configuration.
* **Arguments**: `app_name` (str), `namespace` (str), `container_port` (int).

---

## Claude Desktop Integration

To configure this server to run in Claude Desktop, add the following entry to your configuration file (usually located at `~/.config/Claude/claude_desktop_config.json` on Linux):

```json
{
  "mcpServers": {
    "kubernetes-deployer": {
      "command": "/home/prod-server-2/mcp-k8s-deployer/.venv/bin/python3",
      "args": [
        "/home/prod-server-2/mcp-k8s-deployer/src/server.py"
      ],
      "env": {
        "MCP_K8S_DEFAULT_NFS_STORAGE_CLASS": "nfs",
        "MCP_K8S_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

---

## Transport Selection (Stdio vs SSE)

By default, the server runs over standard input/output (**stdio**) transport, which is suitable for local integrations like Claude Desktop.

If you are publishing the server as a web service or registering it with public HTTP gateways (like **Smithery HTTP endpoints**), you can run the server using **SSE (Server-Sent Events)** transport.

### Running over Stdio (Default)
```bash
python3 src/server.py --transport stdio
```

### Running over SSE (HTTP Web Server)
```bash
python3 src/server.py --transport sse --host 0.0.0.0 --port 8000
```
Or use environment variables:
```bash
export MCP_TRANSPORT=sse
export MCP_PORT=8000
python3 src/server.py
```
*This starts a web server listening on port 8000. The MCP endpoint will be accessible at `http://<your-host>:8000/sse`.*

---

## Typical Execution Flow

1. **User Request**: *"I want to deploy my Node.js application `auth-service` using `node:18` in the `dev` namespace. It needs 5Gi of gp2 storage."*
2. **Storage Decision**: The LLM calls `choose_storage_option_tool(storage_class="gp2", has_existing_pv=False, storage_size="5Gi")`.
3. **Storage Advice**: The server returns that `gp2` is non-default, advising that a PVC will be generated but will rely on dynamic provisioning unless a PV is provided. The LLM presents this choice to the user.
4. **Planning**: The user confirms. The LLM calls `plan_deployment_tool(...)` which returns the planned resources and dry-run apply status.
5. **Confirmation**: The LLM shows the YAML manifests to the user.
6. **Execution**: The user confirms. The LLM calls `apply_deployment_tool(manifests="...", approved=True)`.
7. **Mapping**: The LLM calls `build_cloudflared_target_tool(...)` and prints the final Cloudflare Tunnel ingress target (e.g., `http://auth-service.dev.svc.cluster.local:80`).

---

## Publishing & Distribution

This project includes all necessary configurations to publish and package the MCP server.

### 1. Build and Publish on PyPI
Compile the server into a standard pip package and upload it to PyPI:
```bash
# Install builder and twine
pip install --upgrade build twine

# Build package artifacts
python3 -m build

# Upload package to PyPI
python3 -m twine upload dist/*
```
*Once published, users can install it via `pip install mcp-k8s-deployer` and run the executable `mcp-k8s-deployer`.*

### 2. Package as a Docker Container
Build and distribute a lightweight, secure Docker image:
```bash
# Build the container image
docker build -t your-dockerhub-username/mcp-k8s-deployer:latest .

# Push the container image to Docker Hub
docker push your-dockerhub-username/mcp-k8s-deployer:latest
```

### 3. Deploy with Docker Compose & Cloudflare Tunnel
For a ready-to-run setup that exposes the MCP server over HTTP using a Cloudflare Tunnel:

1. Create a `.env` file in the same directory as `docker-compose.yaml` to hold your Cloudflare token:
   ```env
   CLOUDFLARE_TUNNEL_TOKEN=your_cloudflare_tunnel_token_here
   ```
2. Start the services:
   ```bash
   docker compose up -d
   ```
3. In your Cloudflare Zero Trust Dashboard, set up a **Public Hostname** for your tunnel:
   - **Subdomain/Domain**: `mcp.yourdomain.com`
   - **Service Type**: `HTTP`
   - **URL**: `mcp-server:8000` (or `localhost:8000` if using host network mode)

*Your MCP server is now securely routed at `https://mcp.yourdomain.com/sse`.*


### 4. Share on GitHub
To share the codebase on GitHub, initialize git, register origin, and push:
```bash
git init
git add .
git commit -m "Initial commit of MCP Kubernetes deployer"
git remote add origin https://github.com/yourusername/mcp-k8s-deployer.git
git branch -M main
git push -u origin main
```
*Note: A `.gitignore` file has been preconfigured to exclude environment files and build caches.*

