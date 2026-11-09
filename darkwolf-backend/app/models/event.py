from datetime import datetime

from pydantic import BaseModel, Field


class ThreatEvent(BaseModel):
    source: str
    source_id: str
    collection_run_id: str

    event_type: str
    detected_at: datetime

    observation_id: str
    previous_observation_id: str | None = None

    changed_fields: list[str] = Field(default_factory=list)
    changes: dict = Field(default_factory=dict)
    details: dict = Field(default_factory=dict)