from datetime import datetime

from pydantic import BaseModel, Field


class IncRansomCompany(BaseModel):
    id: str | None = None
    name: str
    country: str | None = None
    revenue: int | float | None = None


class IncRansomAnnouncement(BaseModel):
    id: str
    company: IncRansomCompany
    categories: list[str] = Field(default_factory=list)
    descriptions: list[str] = Field(default_factory=list)
    logo_id: str | None = None
    proof_ids: list[str] = Field(default_factory=list)
    visits: int | None = None
    leak_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    cdn: int | None = None