from datetime import datetime, timezone

from app.db.mongodb import db


collection = db["collection_state"]


def has_source_baseline(source: str) -> bool:
    return collection.find_one({"_id": f"baseline:{source}"}) is not None


def mark_source_baseline(source: str, run_id: str, *, reset: bool = False) -> None:
    baseline = {
        "source": source,
        "baseline_at": datetime.now(timezone.utc),
        "collection_run_id": run_id,
    }
    collection.update_one(
        {"_id": f"baseline:{source}"},
        {"$set" if reset else "$setOnInsert": baseline},
        upsert=True,
    )


def get_event_benchmark() -> datetime:
    """Create and return the first-run cutoff for visible dashboard events."""
    key = "event_visibility_benchmark"
    collection.update_one(
        {"_id": key},
        {"$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    state = collection.find_one({"_id": key}, {"created_at": 1})
    benchmark = state["created_at"]
    # PyMongo decodes BSON datetimes as naive UTC unless tz_aware is enabled.
    return benchmark.replace(tzinfo=timezone.utc) if benchmark.tzinfo is None else benchmark


def reset_event_benchmark(run_ids: list[str]) -> datetime:
    """Hide pre-baseline events and return the new visibility cutoff."""
    benchmark = datetime.now(timezone.utc)
    collection.update_one(
        {"_id": "event_visibility_benchmark"},
        {"$set": {"created_at": benchmark, "baseline_run_ids": run_ids}},
        upsert=True,
    )
    return benchmark
