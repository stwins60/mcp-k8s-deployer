import re
from typing import Dict, List, Optional
import yaml
from pydantic import BaseModel, Field, field_validator, ValidationError

DNS_LABEL_REGEX = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
STORAGE_SIZE_REGEX = re.compile(r"^\d+([kKmMgGtTpPeE]i?)?$")
HOSTNAME_REGEX = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")

class DeploymentInput(BaseModel):
    app_name: str = Field(..., min_length=1, max_length=63)
    image: str = Field(..., min_length=1)
    container_port: int = Field(..., ge=1, le=65535)
    replicas: int = Field(default=1, ge=0)
    namespace: str = Field(..., min_length=1, max_length=63)
    use_persistence: bool = Field(default=False)
    storage_class: Optional[str] = Field(default=None, max_length=63)
    storage_size: Optional[str] = Field(default=None)
    existing_pv_name: Optional[str] = Field(default=None, max_length=63)
    env_vars: Optional[Dict[str, str]] = Field(default=None)
    hostname: Optional[str] = Field(default=None, max_length=253)

    @field_validator("app_name", "namespace", "storage_class", "existing_pv_name")
    @classmethod
    def validate_dns_label(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not DNS_LABEL_REGEX.match(v):
            raise ValueError(
                "Must be a valid DNS subdomain label (lowercase alphanumeric characters or '-', and must start and end with an alphanumeric character)"
            )
        return v

    @field_validator("storage_size")
    @classmethod
    def validate_storage_size(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        if not STORAGE_SIZE_REGEX.match(v):
            raise ValueError(
                "Must be a valid Kubernetes quantity (e.g., 10Gi, 500Mi, 1T)"
            )
        return v

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        if not HOSTNAME_REGEX.match(v):
            raise ValueError(
                "Must be a valid DNS subdomain (lowercase letters, numbers, '.' or '-', starting and ending with alphanumeric)"
            )
        return v

def validate_app_inputs(inputs: dict) -> dict:
    """
    Validates deployment inputs against the DeploymentInput model.
    Returns the validated dictionary or raises ValueError with validation issues.
    """
    try:
        model = DeploymentInput(**inputs)
        return model.model_dump()
    except ValidationError as e:
        errors = []
        for error in e.errors():
            loc = " -> ".join(str(x) for x in error["loc"])
            errors.append(f"[{loc}]: {error['msg']}")
        raise ValueError("Validation error: " + "; ".join(errors))

def validate_manifests_yaml(yaml_str: str) -> List[dict]:
    """
    Parses a multi-document YAML manifest string and runs basic schema validation checks.
    Returns a list of parsed resource dictionaries.
    """
    try:
        resources = list(yaml.safe_load_all(yaml_str))
    except Exception as e:
        raise ValueError(f"Failed to parse YAML manifest: {e}")

    validated_resources = []
    for idx, resource in enumerate(resources):
        if resource is None:
            continue
        if not isinstance(resource, dict):
            raise ValueError(f"Document {idx} is not a valid Kubernetes resource dictionary")
        
        # Check essential fields
        for field in ["apiVersion", "kind", "metadata"]:
            if field not in resource:
                raise ValueError(f"Document {idx} (kind: {resource.get('kind', 'unknown')}) is missing required field '{field}'")
        
        metadata = resource["metadata"]
        if not isinstance(metadata, dict) or "name" not in metadata or not metadata["name"]:
            raise ValueError(f"Document {idx} (kind: {resource.get('kind')}) is missing metadata.name")
            
        validated_resources.append(resource)
        
    return validated_resources
