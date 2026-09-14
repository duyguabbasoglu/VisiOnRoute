"""Object storage value types and evidence media rules (framework-free)."""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


class StorageError(Exception):
    """Storage backend failure (message safe to log; never contains URLs)."""


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    key: str
    size_bytes: int
    content_type: str | None


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    url: str
    method: Literal["POST", "PUT"]
    expires_at: datetime
    # Form fields for S3 presigned POST; empty for PUT uploads.
    fields: dict[str, str] = field(default_factory=dict)
    # Headers the client must send (e.g. Content-Type for PUT uploads).
    headers: dict[str, str] = field(default_factory=dict)


# Evidence media accepted from cameras/integrations/users, with the magic bytes
# the stored object must start with. Anything else is rejected.
EVIDENCE_MEDIA_TYPES: dict[str, str] = {
    "image/jpeg": "snapshot",
    "image/png": "snapshot",
    "video/mp4": "clip",
}

_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.-]{0,511}$")


def sniff_media_type(head: bytes) -> str | None:
    """Detect the media type from leading bytes (never trust the client's claim)."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "video/mp4"
    return None


def evidence_object_key(organization_id: uuid.UUID, evidence_id: uuid.UUID) -> str:
    """Opaque key: no filenames, event types or personal data in object names."""
    return f"orgs/{organization_id}/evidence/{evidence_id}"


def export_object_key(organization_id: uuid.UUID, request_id: uuid.UUID) -> str:
    return f"orgs/{organization_id}/privacy-exports/{request_id}.zip"


def report_object_key(organization_id: uuid.UUID, artifact_id: uuid.UUID, extension: str) -> str:
    return f"orgs/{organization_id}/reports/{artifact_id}.{extension}"


def is_valid_object_key(key: str) -> bool:
    return bool(_KEY_RE.fullmatch(key)) and ".." not in key.split("/")


def safe_download_filename(name: str, fallback: str) -> str:
    """ASCII-only, path-free filename for Content-Disposition headers."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized.rsplit("/", 1)[-1]).strip("-.")
    return (cleaned or fallback)[:100]
