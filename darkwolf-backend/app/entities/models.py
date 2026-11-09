from datetime import datetime

from pydantic import BaseModel, Field


class Organization(BaseModel):
    id: str

    name: str

    source: str
    source_ids: dict[str, str] = Field(default_factory=dict)

    country_id: str | None = None
    revenue: int | float | None = None

    first_seen: datetime | None = None
    last_seen: datetime | None = None


class Country(BaseModel):
    id: str

    name: str
    normalized_name: str

    source: str | None = None


class Industry(BaseModel):
    id: str

    name: str
    normalized_name: str

    source: str | None = None


class Domain(BaseModel):
    id: str

    domain: str
    normalized_domain: str

    organization_id: str | None = None

    first_seen: datetime | None = None
    last_seen: datetime | None = None


class ThreatActor(BaseModel):
    id: str

    name: str
    normalized_name: str

    source: str | None = None


class Source(BaseModel):
    id: str

    name: str
    source_type: str

    ransomware_group: str | None = None

    url: str | None = None


class Leak(BaseModel):
    id: str

    source: str
    source_id: str

    organization_id: str | None = None

    categories: list[str] = Field(default_factory=list)
    proof_ids: list[str] = Field(default_factory=list)

    leak_at: datetime | None = None

    first_seen: datetime | None = None
    last_seen: datetime | None = None