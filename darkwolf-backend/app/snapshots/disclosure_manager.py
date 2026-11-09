from datetime import datetime, timezone

from app.models.disclosure_observation import DisclosureObservation
from app.sites.inc_ransom.disclosure_models import IncRansomDisclosure
from app.snapshots.disclosure_hasher import (
    calculate_disclosure_content_hash,
)


def build_disclosure_observation(
    disclosure: IncRansomDisclosure,
    collection_run_id: str,
    raw_evidence_id: str | None = None,
) -> DisclosureObservation:

    observed_at = datetime.now(timezone.utc)

    data = {
        "title": disclosure.title,
        "categories": disclosure.categories,
        "content": disclosure.content,
        "size": disclosure.size,
        "leak_at": disclosure.leak_at,
        "cdn_id": disclosure.cdn_id,
        "cdn_onion": disclosure.cdn_onion,
        "cdn_clear": disclosure.cdn_clear,
    }

    content_hash = calculate_disclosure_content_hash(data)

    return DisclosureObservation(
        source="inc_ransom",
        disclosure_id=disclosure.id,
        announcement_id=disclosure.announcement_id,
        collection_run_id=collection_run_id,
        raw_evidence_id=raw_evidence_id,

        observed_at=observed_at,

        title=disclosure.title,
        categories=disclosure.categories,
        content=disclosure.content,
        size=disclosure.size,

        leak_at=disclosure.leak_at,
        source_created_at=disclosure.created_at,

        cdn_id=disclosure.cdn_id,
        cdn_onion=disclosure.cdn_onion,
        cdn_clear=disclosure.cdn_clear,

        content_hash=content_hash,
    )