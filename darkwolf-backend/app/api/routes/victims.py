from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.api.dashboard import canonical_country
from app.db.collection_state import get_event_benchmark
from app.db.mongodb import db
from app.entities.mapper import build_entity_id
from app.entities.formatting import display_organization_name
from app.entities.source_groups import source_slugs_for_group
from app.events.new_victim_policy import SOURCE_DATE_GATED_DISCOVERIES, has_recent_source_date


router = APIRouter(
    prefix="/api/v1/victims",
    tags=["Victims"],
)


observations = db["observations"]
events = db["events"]
sources = db["sources"]


def _as_utc(value):
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _range_cutoff(range_value: str, now: datetime):
    if range_value.casefold() == "all":
        return None
    try:
        days = int(range_value)
    except (TypeError, ValueError):
        days = 30
    if days not in {1, 7, 30, 90}:
        days = 30
    return now - timedelta(days=days)


@router.get("")
def get_victims(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    group: str | None = None,
    range: str = "30",
    search: str | None = None,
    status: str = "all",
    sort_by: str = "leak_date",
    sort_order: str = "desc",
):
    """Paginated latest victim snapshots with source-date and baseline-aware filters."""
    now = datetime.now(timezone.utc)
    cutoff = _range_cutoff(range, now)
    benchmark = get_event_benchmark()
    baseline_cutoff = max(cutoff or benchmark, benchmark)
    source_slugs = source_slugs_for_group(group)

    event_query = {"event_type": "VICTIM_DISCOVERED", "detected_at": {"$gte": benchmark}}
    if source_slugs is not None:
        event_query["source"] = {"$in": source_slugs}
    first_discovered = {}
    for event in events.find(event_query, {"source": 1, "source_id": 1, "detected_at": 1}).sort("detected_at", 1):
        key = (event.get("source"), event.get("source_id"))
        first_discovered.setdefault(key, event.get("detected_at"))

    match = {"source_id": {"$ne": None}}
    if source_slugs is not None:
        if not source_slugs:
            return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0,
                    "summary": {"total_victims": 0, "new_victims": 0, "yet_to_publish": 0,
                                "published_victims": 0, "active_groups": 0, "countries": 0}}
        match["source"] = {"$in": source_slugs}

    pipeline = [
        {"$match": match},
        {"$sort": {"observed_at": -1, "_id": -1}},
        {"$group": {"_id": {"source": "$source", "source_id": "$source_id"}, "snapshot": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$snapshot"}},
    ]
    groups_by_slug = {}
    source_records_by_id = {
        item.get("id"): item
        for item in sources.find({}, {"_id": 0, "id": 1, "name": 1, "url": 1, "ransomware_group": 1})
        if item.get("id")
    }
    for source_slug in observations.distinct("source", match):
        source_record = source_records_by_id.get(build_entity_id("source", source_slug))
        if source_record:
            groups_by_slug[source_slug] = source_record.get("ransomware_group")

    candidates = []
    for observation in observations.aggregate(pipeline, allowDiskUse=True):
        source_name = observation.get("source")
        source_id = observation.get("source_id")
        identity = (source_name, source_id)
        ransomware_group = groups_by_slug.get(source_name) or observation.get("ransomware_group")
        is_kazu = (ransomware_group or "").casefold() == "kazu"
        is_qilin = (ransomware_group or "").casefold() == "qilin"
        source_publication_status = observation.get("source_publication_status")
        source_created_at = _as_utc(observation.get("source_created_at"))
        unpublished_qilin = is_qilin and source_publication_status != "published"
        leak_at = (
            None
            if is_kazu or unpublished_qilin
            else _as_utc(observation.get("leak_at")) or source_created_at
        )
        discovered_at = _as_utc(first_discovered.get(identity))
        estimated_publish_at = _as_utc(observation.get("estimated_publish_at"))
        countdown_captured_at = _as_utc(observation.get("countdown_captured_at"))

        if cutoff is not None:
            if leak_at:
                if leak_at < cutoff:
                    continue
            elif not (
                (discovered_at and discovered_at >= baseline_cutoff)
                or (estimated_publish_at and countdown_captured_at and countdown_captured_at >= cutoff)
            ):
                # Scraping an old undated record again must not make it appear new.
                continue

        # An explicit pending state must take precedence over the listing/leak
        # date: sources commonly show when a victim was listed while its data
        # is still behind a publication countdown.
        if source_publication_status == "yet_to_publish":
            publication_status = "yet_to_publish"
        elif source_publication_status == "published":
            publication_status = "published"
        elif estimated_publish_at:
            publication_status = "yet_to_publish" if estimated_publish_at > now else "awaiting_confirmation"
        elif leak_at:
            publication_status = "published"
        else:
            publication_status = "listed"

        is_new = bool(discovered_at and discovered_at >= baseline_cutoff)
        if source_name in SOURCE_DATE_GATED_DISCOVERIES:
            is_new = has_recent_source_date(leak_at, now)
        country = observation.get("country")
        canonical = canonical_country(country)
        country_code = canonical[0] if canonical else None
        source = source_records_by_id.get(build_entity_id("source", source_name), {})
        row = {
            "id": f"{source_name}:{source_id}",
            "source_id": source_id,
            "source": source_name,
            "source_name": (source or {}).get("name") or source_name,
            "source_url": (source or {}).get("url"),
            "organization": display_organization_name(observation.get("company_name"), ransomware_group),
            "country": country,
            "country_code": country_code,
            "domain": observation.get("domain"),
            "ransomware_group": ransomware_group,
            "leak_date": leak_at,
            "observed_at": _as_utc(observation.get("observed_at")),
            "first_discovered_at": discovered_at,
            "estimated_publish_at": estimated_publish_at,
            "countdown_captured_at": countdown_captured_at,
            "countdown_seconds_at_capture": observation.get("countdown_seconds_at_capture"),
            "countdown_raw": observation.get("countdown_raw"),
            "countdown_remaining_seconds": max(0, int((estimated_publish_at - now).total_seconds())) if estimated_publish_at else None,
            "publication_status": publication_status,
            "is_new": is_new,
        }
        candidates.append(row)

    summary = {
        "total_victims": len(candidates),
        "new_victims": sum(1 for row in candidates if row["is_new"]),
        "yet_to_publish": sum(1 for row in candidates if row["publication_status"] == "yet_to_publish"),
        "published_victims": sum(1 for row in candidates if row["publication_status"] == "published"),
        "active_groups": len({row["ransomware_group"] for row in candidates if row["ransomware_group"]}),
        "countries": len({row["country_code"] for row in candidates if row["country_code"]}),
    }

    search_value = (search or "").strip().casefold()
    if search_value:
        candidates = [row for row in candidates if search_value in " ".join(str(row.get(key) or "") for key in
                      ("organization", "domain", "ransomware_group", "source_name")).casefold()]
    if status.casefold() != "all":
        if status.casefold() == "new":
            candidates = [row for row in candidates if row["is_new"]]
        else:
            candidates = [row for row in candidates if row["publication_status"] == status.casefold()]

    allowed_sort = {"organization", "ransomware_group", "domain", "leak_date", "estimated_publish_at", "publication_status"}
    if sort_by not in allowed_sort:
        sort_by = "leak_date"
    reverse = sort_order.casefold() != "asc"
    candidates.sort(
        key=lambda row: (
            row.get(sort_by) is not None,
            row.get(sort_by).casefold() if isinstance(row.get(sort_by), str) else row.get(sort_by) or datetime.min.replace(tzinfo=timezone.utc),
            row.get("organization", "").casefold(),
        ),
        reverse=reverse,
    )
    total = len(candidates)
    start = (page - 1) * page_size
    return {
        "items": candidates[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "summary": summary,
    }


@router.get("/recent")
def get_recent_victims(limit: int = 5, group: str | None = None, range: str = "30"):
    now = datetime.now(timezone.utc)
    if range == "all":
        cutoff = None
    else:
        try:
            days = int(range)
        except (TypeError, ValueError):
            days = 30
        cutoff = now - timedelta(days=1 if days == 1 else days)
    source_slugs = source_slugs_for_group(group)

    # A missing source date is eligible only when the victim was first
    # discovered after the active baseline and within the same 48-hour window.
    discovery_query = {
        "event_type": "VICTIM_DISCOVERED",
        "detected_at": {"$gte": max(cutoff or get_event_benchmark(), get_event_benchmark())},
    }
    if source_slugs is not None:
        discovery_query["source"] = {"$in": source_slugs}

    undated_discoveries: dict[str, set[str]] = {}
    for event in events.find(discovery_query, {"source": 1, "source_id": 1}):
        source = event.get("source")
        source_id = event.get("source_id")
        if source in SOURCE_DATE_GATED_DISCOVERIES:
            continue
        if source and source_id:
            undated_discoveries.setdefault(source, set()).add(source_id)

    # Future leak_at values are often estimated publication deadlines. Keep
    # those in the victims page's countdown fields, but never treat them as
    # recent leaks or let them sort ahead of confirmed past leak dates here.
    dated_leak_query = {"$lte": now}
    if cutoff is not None:
        dated_leak_query["$gte"] = cutoff
    query_clauses = [{"leak_at": dated_leak_query}]
    query_clauses.extend(
        {
            "source": source,
            "source_id": {"$in": list(source_ids)},
            "leak_at": None,
        }
        for source, source_ids in undated_discoveries.items()
    )
    query = {"$or": query_clauses}
    if source_slugs is not None:
        query["source"] = {"$in": source_slugs}

    documents = (
        observations
        .find(
            query,
            {
                "_id": 0,
                "source_id": 1,
                "source": 1,
                "company_name": 1,
                "country": 1,
                "domain": 1,
                "leak_at": 1,
                "observed_at": 1,
            },
        )
        .sort([("leak_at", -1), ("observed_at", -1)])
    )

    results = []
    seen_source_ids = set()

    for document in documents:
        source_id = document.get("source_id")
        source_name = document.get("source")

        # Skip repeated observations of the same victim within its source.
        identity = (source_name, source_id)
        if identity in seen_source_ids:
            continue

        seen_source_ids.add(identity)

        source_record_id = build_entity_id("source", source_name) if source_name else None
        source = sources.find_one(
            {"id": source_record_id},
            {"_id": 0, "ransomware_group": 1},
        ) if source_record_id else None
        ransomware_group = source.get("ransomware_group") if source else None

        # Kazu's displayed date is a countdown deadline, not a confirmed
        # victim leak date. Older observations may still contain that value;
        # never expose it as a leak date in the dashboard.
        leak_date = None if (ransomware_group or "").casefold() == "kazu" else document.get("leak_at")

        results.append(
            {
                "id": source_id,
                "organization": display_organization_name(
                    document.get("company_name"), ransomware_group
                ),
                "country": document.get(
                    "country"
                ),
                "domain": document.get(
                    "domain"
                ),
                "leak_date": leak_date,
                "observed_at": document.get(
                    "observed_at"
                ),
                "ransomware_group": ransomware_group,
                "status": "new",
            }
        )

    # Source leak dates take precedence over scrape timestamps. Sort undated,
    # newly discovered entries after dated leaks, using observation time only
    # to order those undated entries among themselves.
    results.sort(
        key=lambda item: (
            item.get("leak_date") is not None,
            item.get("leak_date")
            or _as_utc(item.get("observed_at"))
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return results[:limit]
