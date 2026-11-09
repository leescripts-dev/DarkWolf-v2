from pydantic import BaseModel, Field


class CollectionResult(BaseModel):
    collection_run_id: str
    source: str
    page: int

    announcements_found: int = 0
    observations_saved: int = 0
    first_observations: int = 0
    content_changed: int = 0
    unchanged: int = 0
    events_generated: int = 0

    disclosures_found: int = 0
    disclosure_observations_saved: int = 0
    disclosure_first_observations: int = 0
    disclosure_content_changed: int = 0
    disclosure_unchanged: int = 0
    disclosure_events_generated: int = 0

    errors: list[dict] = Field(default_factory=list)


class HistoricalCollectionResult(BaseModel):
    collection_run_id: str
    source: str

    pages_processed: int = 0
    expected_pages: int = 0

    announcements_expected: int = 0
    announcements_found: int = 0

    observations_saved: int = 0
    first_observations: int = 0
    content_changed: int = 0
    unchanged: int = 0

    events_generated: int = 0

    errors: list[dict] = Field(default_factory=list)