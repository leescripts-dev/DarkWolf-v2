from app.db.mongodb import db
from app.db.events import save_event
from app.models.event import ThreatEvent
from app.events.new_victim_policy import SOURCE_DATE_GATED_DISCOVERIES, has_recent_source_date
from app.sites.html_leak_sites.registry import HTML_LEAK_SITES


def backfill_initial_listing_discoveries() -> dict:
    """Record each baseline listing as first observed by DarkWolf."""
    observations = db["observations"]
    events = db["events"]
    created = 0
    skipped = 0

    for site in HTML_LEAK_SITES:
        source_ids = observations.distinct("source_id", {"source": site.slug})
        for source_id in source_ids:
            existing = events.find_one({
                "source": site.slug,
                "source_id": source_id,
                "event_type": "VICTIM_DISCOVERED",
            })
            if existing:
                skipped += 1
                continue

            observation = observations.find_one(
                {"source": site.slug, "source_id": source_id},
                sort=[("observed_at", 1)],
            )
            if not observation:
                continue
            if (
                site.slug in SOURCE_DATE_GATED_DISCOVERIES
                and not has_recent_source_date(observation.get("leak_at"))
            ):
                skipped += 1
                continue

            save_event(ThreatEvent(
                source=site.slug,
                source_id=source_id,
                collection_run_id=observation["collection_run_id"],
                event_type="VICTIM_DISCOVERED",
                detected_at=observation["observed_at"],
                observation_id=str(observation["_id"]),
                details={
                    "baseline_import": True,
                    "discovery_basis": "first_observed_by_darkwolf",
                    "listing_url": observation.get("listing_url"),
                },
            ))
            created += 1

    return {"baseline_discoveries_created": created, "already_present": skipped}
