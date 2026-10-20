"""Connection-request data model for the 3 kinds of LanceDB connection lsql supports:
a local on-disk path, a direct object-storage URI (s3://, gs://, az://), and a LanceDB
Cloud/Enterprise remote connection (db:// URI)."""

from dataclasses import dataclass, field
from typing import Dict, Optional

OBJECT_STORAGE_PROVIDERS = ("s3", "azure", "gcs")

# (form label, storage_options key) pairs per provider, for the Object Storage tab.
S3_FIELDS = [
    ("Access Key ID", "aws_access_key_id"),
    ("Secret Access Key", "aws_secret_access_key"),
    ("Session Token", "aws_session_token"),
    ("Region", "aws_region"),
]
AZURE_FIELDS = [
    ("Account Name", "account_name"),
    ("Account Key", "account_key"),
]
GCS_FIELDS = [
    ("Service Account JSON Path", "service_account"),
]

PROVIDER_FIELDS = {
    "s3": S3_FIELDS,
    "azure": AZURE_FIELDS,
    "gcs": GCS_FIELDS,
}

# Fields whose values should be masked in the UI (Input(password=True)).
SECRET_FIELD_KEYS = {"aws_secret_access_key", "aws_session_token", "account_key"}


@dataclass
class ConnectionRequest:
    kind: str  # "local" | "object_storage" | "cloud"
    uri: str
    provider: Optional[str] = None  # object_storage only: "s3" | "azure" | "gcs"
    storage_options: Dict[str, str] = field(default_factory=dict)  # object_storage only
    api_key: Optional[str] = None  # cloud only
    region: Optional[str] = None  # cloud only, default "us-east-1"
    host_override: Optional[str] = None  # cloud only

    @staticmethod
    def local(path: str) -> "ConnectionRequest":
        return ConnectionRequest(kind="local", uri=path)
