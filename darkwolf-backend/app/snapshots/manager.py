from datetime import datetime, timezone

from app.models.observation import Observation
from app.sites.inc_ransom.models import IncRansomAnnouncement
from app.snapshots.hasher import calculate_content_hash


def build_observation(
    announcement: IncRansomAnnouncement,
    collection_run_id: str,
    raw_evidence_id: str | None = None,
) -> Observation:

    observed_at = datetime.now(timezone.utc)

    data = {
        "company_name": announcement.company.name,
        "company_id": announcement.company.id,
        "country": announcement.company.country,
        "revenue": announcement.company.revenue,
        "categories": announcement.categories,
        "descriptions": announcement.descriptions,
        "proof_ids": announcement.proof_ids,
        "logo_id": announcement.logo_id,
        "leak_at": announcement.leak_at,
        "cdn": announcement.cdn,
    }

    content_hash = calculate_content_hash(data)

    return Observation(
        source="inc_ransom",
        source_id=announcement.id,
        collection_run_id=collection_run_id,
        raw_evidence_id=raw_evidence_id,

        observed_at=observed_at,

        company_name=data["company_name"],
        company_id=data["company_id"],
        country=data["country"],
        revenue=data["revenue"],
        categories=data["categories"],
        descriptions=data["descriptions"],
        proof_ids=data["proof_ids"],
        logo_id=data["logo_id"],

        visits=announcement.visits,

        leak_at=data["leak_at"],
        source_created_at=announcement.created_at,
        source_updated_at=announcement.updated_at,
        cdn=data["cdn"],

        content_hash=content_hash,
    )