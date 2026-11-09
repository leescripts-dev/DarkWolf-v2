from copy import deepcopy
from datetime import datetime, timezone

from app.models.raw_evidence import RawEvidence
from app.snapshots.raw_hasher import calculate_response_hash


def sanitize_response_body(body: dict) -> tuple[dict, list[str]]:
    sanitized = deepcopy(body)
    redacted_fields = []

    def redact(value, path=""):
        if isinstance(value, dict):
            for key in list(value.keys()):
                current_path = f"{path}.{key}" if path else key

                if key.lower() == "password":
                    value[key] = "[REDACTED]"
                    redacted_fields.append(current_path)
                else:
                    redact(value[key], current_path)

        elif isinstance(value, list):
            for index, item in enumerate(value):
                redact(item, f"{path}[{index}]")

    redact(sanitized)

    return sanitized, redacted_fields


def build_raw_evidence(
    source: str,
    source_id: str | None,
    collection_run_id: str,
    endpoint: str,
    response,
    metadata: dict | None = None,
) -> RawEvidence:

    original_body = response.json()

    response_hash = calculate_response_hash(original_body)

    sanitized_body, redacted_fields = sanitize_response_body(
        original_body
    )

    return RawEvidence(
        source=source,
        source_id=source_id,
        collection_run_id=collection_run_id,
        endpoint=endpoint,
        method="GET",
        captured_at=datetime.now(timezone.utc),
        status_code=response.status_code,
        content_type=response.headers.get("content-type"),
        response_hash=response_hash,
        response_body=sanitized_body,
        redacted_fields=redacted_fields,
        metadata=metadata or {},
    )