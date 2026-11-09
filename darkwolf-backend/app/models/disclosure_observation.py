from datetime import datetime

from pydantic import BaseModel, Field


class DisclosureObservation(BaseModel):
    source: str
    disclosure_id: str
    announcement_id: str
    collection_run_id: str
    raw_evidence_id: str | None = None

    observed_at: datetime

    title: str
    categories: list[str] = Field(default_factory=list)
    content: list[str] = Field(default_factory=list)
    size: str | None = None

    leak_at: datetime | None = None
    source_created_at: datetime | None = None

    cdn_id: str | None = None
    cdn_onion: str | None = None
    cdn_clear: str | None = None

    content_hash: str