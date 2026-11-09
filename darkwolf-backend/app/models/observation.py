from datetime import datetime

from pydantic import BaseModel, Field


class Observation(BaseModel):
    source: str
    source_id: str
    collection_run_id: str
    raw_evidence_id: str | None = None

    source_display_name: str | None = None
    ransomware_group: str | None = None
    source_url: str | None = None
    listing_url: str | None = None

    observed_at: datetime
    company_name: str
    company_id: str | None = None
    domain: str | None = None
    country: str | None = None
    revenue: int | float | None = None
    categories: list[str] = Field(default_factory=list)
    descriptions: list[str] = Field(default_factory=list)
    proof_ids: list[str] = Field(default_factory=list)
    logo_id: str | None = None
    visits: int | None = None
    leak_at: datetime | None = None
    estimated_publish_at: datetime | None = None
    countdown_captured_at: datetime | None = None
    countdown_seconds_at_capture: int | None = None
    countdown_raw: str | None = None
    source_publication_status: str | None = None
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    cdn: int | None = None
    content_hash: str
