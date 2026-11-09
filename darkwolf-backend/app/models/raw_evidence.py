from datetime import datetime

from pydantic import BaseModel, Field


class RawEvidence(BaseModel):
    source: str
    source_id: str | None = None
    collection_run_id: str

    endpoint: str
    method: str
    captured_at: datetime

    status_code: int
    content_type: str | None = None

    response_hash: str

    response_body: dict = Field(default_factory=dict)

    redacted_fields: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)