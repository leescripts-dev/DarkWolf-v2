from collections import defaultdict

from app.db.events import save_event
from app.db.mongodb import db
from app.events.detector import detect_events
from app.models.event import ThreatEvent
from app.snapshots.differ import compare_observations


def backfill_observation_events() -> dict:
    """Reconstruct missing discovery and change events from saved snapshots.

    Events are deduplicated by observation and event type, making the backfill
    safe to rerun. Historical event timestamps remain the observation times;
    the dashboard benchmark keeps pre-rollout history out of current views.
    """
    observations = db["observations"]
    events = db["events"]
    existing = {
        (event.get("observation_id"), event.get("event_type"))
        for event in events.find({}, {"observation_id": 1, "event_type": 1})
    }

    by_record: dict[tuple[str, str], list[dict]] = defaultdict(list)
    cursor = observations.find({}).sort(
        [("source", 1), ("source_id", 1), ("observed_at", 1), ("_id", 1)]
    )
    for observation in cursor:
        by_record[(observation["source"], observation["source_id"])].append(observation)

    created = 0
    skipped = 0
    records_scanned = 0
    for (source, source_id), snapshots in by_record.items():
        previous = None
        for observation in snapshots:
            records_scanned += 1
            current_id = str(observation["_id"])
            comparison = compare_observations(previous, observation)
            is_first = previous is None
            for event_data in detect_events(comparison):
                key = (current_id, event_data["event_type"])
                if key in existing:
                    skipped += 1
                    continue
                details = {
                    **event_data.get("details", {}),
                    "listing_url": observation.get("listing_url"),
                    "backfilled": True,
                }
                if is_first:
                    details.update({
                        "baseline_import": True,
                        "discovery_basis": "first_observed_by_darkwolf",
                    })
                save_event(ThreatEvent(
                    source=source,
                    source_id=source_id,
                    collection_run_id=observation["collection_run_id"],
                    event_type=event_data["event_type"],
                    detected_at=observation["observed_at"],
                    observation_id=current_id,
                    previous_observation_id=str(previous["_id"]) if previous else None,
                    changed_fields=event_data["changed_fields"],
                    changes=event_data["changes"],
                    details=details,
                ))
                existing.add(key)
                created += 1
            previous = observation

    return {
        "sources": len({source for source, _ in by_record}),
        "source_records": len(by_record),
        "observations_scanned": records_scanned,
        "events_created": created,
        "existing_events_skipped": skipped,
    }
