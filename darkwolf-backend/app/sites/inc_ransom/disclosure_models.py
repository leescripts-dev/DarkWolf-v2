from datetime import datetime

from pydantic import BaseModel, Field


class IncRansomDisclosure(BaseModel):
    id: str
    announcement_id: str

    title: str
    categories: list[str] = Field(default_factory=list)
    content: list[str] = Field(default_factory=list)

    size: str | None = None

    leak_at: datetime | None = None
    created_at: datetime | None = None

    cdn_id: str | None = None
    cdn_onion: str | None = None
    cdn_clear: str | None = None