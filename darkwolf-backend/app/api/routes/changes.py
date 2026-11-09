from datetime import datetime, timedelta, timezone
import re

from bson import ObjectId

from fastapi import APIRouter, HTTPException

from app.db.mongodb import db
from app.db.collection_state import get_event_benchmark
from app.db.screenshots import get_screenshot
from app.entities.mapper import build_entity_id
from app.entities.formatting import display_organization_name
from app.entities.source_groups import source_slugs_for_group
from app.events.new_victim_policy import SOURCE_DATE_GATED_DISCOVERIES, has_recent_source_date


router = APIRouter(
    prefix="/api/v1/changes",
    tags=["Changes"],
)


events = db["events"]
observations = db["observations"]
disclosure_observations = db["disclosure_observations"]
organizations = db["organizations"]
domains = db["domains"]
sources = db["sources"]
raw_evidence = db["raw_evidence"]


SOURCE_NAME = "inc_ransom"


def _date_timestamp(value) -> float:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            pass
    return 0


def _source_metadata_date(observation: dict | None):
    if not observation:
        return None
    for field in ("leak_at", "source_created_at", "source_updated_at"):
        value = observation.get(field)
        if value is not None:
            return value
    return None


def get_object_id(value: str | None):

    if not value:
        return None

    try:
        return ObjectId(value)

    except Exception:
        return None


def clean_document(document):

    """
    Convert MongoDB ObjectIds into strings so the
    document can safely be returned through FastAPI.
    """

    if document is None:
        return None

    if isinstance(document, ObjectId):
        return str(document)

    if isinstance(document, dict):
        return {
            key: clean_document(value)
            for key, value in document.items()
        }

    if isinstance(document, list):
        return [
            clean_document(value)
            for value in document
        ]

    return document


def get_observation(
    observation_id: str | None,
    source_name: str | None = None,
):

    """
    Resolve a normal victim observation.

    observation_id may be either:

    - MongoDB _id
    - source_id
    """

    if not observation_id:
        return None

    object_id = get_object_id(
        observation_id
    )

    if object_id:

        observation = observations.find_one(
            {"_id": object_id}
        )

        if observation:
            return observation

    return observations.find_one({
        "source": source_name or SOURCE_NAME,
        "source_id": observation_id,
    })


def get_disclosure_observation(
    observation_id: str | None,
):

    """
    Resolve a disclosure observation by its
    MongoDB _id.
    """

    if not observation_id:
        return None

    object_id = get_object_id(
        observation_id
    )

    if not object_id:
        return None

    return disclosure_observations.find_one(
        {"_id": object_id}
    )


def get_announcement_observation(
    announcement_id: str | None,
):

    """
    Resolve the normal victim observation associated
    with a disclosure through announcement_id.
    """

    if not announcement_id:
        return None

    return observations.find_one(
        {
            "source": SOURCE_NAME,
            "source_id": announcement_id,
        }
    )


def get_raw_evidence(
    raw_evidence_id: str | None,
):

    if not raw_evidence_id:
        return None

    object_id = get_object_id(
        raw_evidence_id
    )

    if object_id:

        evidence = raw_evidence.find_one(
            {"_id": object_id}
        )

        if evidence:
            return evidence

    return raw_evidence.find_one(
        {"id": raw_evidence_id}
    )


def clean_evidence_with_screenshot(document):
    cleaned = clean_document(document)
    if not cleaned:
        return None
    screenshot_id = (cleaned.get("metadata") or {}).get("screenshot_id")
    if screenshot_id:
        cleaned["screenshot_url"] = f"/api/v1/evidence/screenshots/{screenshot_id}"
    return cleaned


def get_organization(
    observation: dict | None,
):

    if not observation:
        return None

    company_id = observation.get(
        "company_id"
    )

    if not company_id:
        return None

    return organizations.find_one(
        {"id": company_id},
        {"_id": 0},
    )


def get_domains(
    organization_id: str | None,
):

    if not organization_id:
        return []

    documents = domains.find(
        {
            "organization_id": organization_id
        },
        {
            "_id": 0,
            "domain": 1,
        },
    )

    return sorted(
        {
            document["domain"]
            for document in documents
            if document.get("domain")
        }
    )


def get_ransomware_group(source_name: str = SOURCE_NAME):

    source_id = build_entity_id(
        "source",
        source_name,
    )

    source = sources.find_one(
        {"id": source_id},
        {
            "_id": 0,
            "ransomware_group": 1,
        },
    )

    if not source:
        return None

    return source.get(
        "ransomware_group"
    )


def _human_value(value) -> str:
    if value is None or value == "":
        return "not listed"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_human_value(item) for item in value) or "none"
    if isinstance(value, dict):
        return ", ".join(f"{key}: {_human_value(item)}" for key, item in value.items())
    return str(value).strip()


def _text_indicates_disclosure(value) -> bool:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    positive = ("published", "publicly available", "data disclosed", "data leaked", "database leaked", "files leaked", "leak is available", "download available")
    pending = ("will be published", "awaiting publication", "pending exposure", "not yet published")
    for item in values:
        text = _human_value(item).casefold()
        if any(phrase in text for phrase in pending):
            continue
        if any(phrase in text for phrase in positive):
            return True
    return False


def build_change_description(
    event_type: str,
    changes: dict,
    current_snapshot: dict | None = None,
    detected_at=None,
) -> str:
    """Turn normalized event diffs into concise, source-agnostic prose."""
    current_snapshot = current_snapshot or {}
    changes = changes if isinstance(changes, dict) else {}
    event_date = detected_at or current_snapshot.get("leak_at") or current_snapshot.get("source_created_at")
    date_text = ""
    if event_date:
        try:
            parsed = event_date if isinstance(event_date, datetime) else datetime.fromisoformat(str(event_date).replace("Z", "+00:00"))
            date_text = f" on {parsed.strftime('%d/%m/%Y')}"
        except (TypeError, ValueError):
            date_text = f" on {_human_value(event_date)}"

    if event_type in {"DISCLOSURE_DISCOVERED", "VICTIM_DISCOVERED_AND_DISCLOSED"}:
        size = current_snapshot.get("size") or current_snapshot.get("storage_gb") or current_snapshot.get("leak_size")
        if not size:
            description_text = " ".join(_human_value(item) for item in current_snapshot.get("descriptions", []))
            match = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(TB|GB|MB)\b", description_text, re.IGNORECASE)
            if match:
                size = f"{match.group(1)} {match.group(2).upper()}"
        has_download_link = any(
            isinstance(current_snapshot.get(field), str)
            and current_snapshot[field].strip().startswith(("http://", "https://"))
            for field in ("cdn_onion", "cdn_clear", "download_url", "url")
        )
        text = "Data has been disclosed for this victim"
        if has_download_link:
            text += "; a CDN endpoint is listed"
        return f"{text}, listed leak size {_human_value(size)}{date_text}" if size else f"{text}{date_text}."
    if event_type == "VICTIM_DISCOVERED":
        return f"Victim was first listed by the monitored source{date_text}."

    field_labels = {
        "size": "Leak size", "storage_gb": "Leak size", "leak_size": "Leak size",
        "file_count": "File count", "files": "Files", "leak_at": "Leak date",
        "source_created_at": "Listing date", "source_updated_at": "Listing update date",
        "source_publication_status": "Publication status", "published": "Publication status",
        "cdn_id": "Download location", "cdn_onion": "Download location", "cdn_clear": "Download location",
        "content": "Disclosure details", "descriptions": "Victim details", "description": "Victim details",
        "categories": "Data categories", "country": "Country", "domain": "Domain",
        "company_name": "Organization name", "title": "Disclosure title", "revenue": "Revenue",
    }
    summaries = []
    for field, change in changes.items():
        label = field_labels.get(field, field.replace("_", " ").capitalize())
        if not isinstance(change, dict) or not ("previous" in change or "current" in change):
            summaries.append(f"{label} updated to {_human_value(change)}")
            continue
        previous = change.get("previous")
        current = change.get("current")
        if field in {"cdn_id", "cdn_onion", "cdn_clear"}:
            summaries.append("A CDN endpoint was added or updated" if current else "A CDN endpoint is no longer listed")
        elif previous in (None, "", [], {}) and current not in (None, "", [], {}):
            summaries.append(f"{label} was added ({_human_value(current)})")
        elif current in (None, "", [], {}) and previous not in (None, "", [], {}):
            summaries.append(f"{label} was removed (previously {_human_value(previous)})")
        elif field in {"size", "storage_gb", "leak_size"}:
            summaries.append(f"Leak size changed from {_human_value(previous)} to {_human_value(current)}{date_text}")
        elif field in {"leak_at", "source_created_at", "source_updated_at"}:
            summaries.append(f"{label} changed from {_human_value(previous)} to {_human_value(current)}")
        elif field in {"descriptions", "description", "content"}:
            if _text_indicates_disclosure(current) and not _text_indicates_disclosure(previous):
                summaries.append("Data disclosure status changed: victim data is now listed as published or disclosed")
            elif _text_indicates_disclosure(previous) and not _text_indicates_disclosure(current):
                summaries.append("Source no longer lists the victim data as published or disclosed")
            elif field == "content":
                summaries.append("Disclosure details were updated")
            else:
                summaries.append("Victim description was updated")
        else:
            summaries.append(f"{label} changed from {_human_value(previous)} to {_human_value(current)}")

    if summaries:
        return ". ".join(summary.rstrip(".") for summary in summaries) + "."
    if event_type.startswith("DISCLOSURE_"):
        return f"Disclosure information was updated{date_text}."
    readable_type = event_type.replace("_", " ").lower()
    return f"{readable_type.capitalize() or 'Intelligence'} was detected{date_text}."


def is_disclosure_event(
    event: dict,
) -> bool:

    return event.get(
        "event_type",
        ""
    ).startswith("DISCLOSURE_")


def resolve_event_context(
    event: dict,
):

    """
    Resolve the correct current/previous snapshots
    depending on whether the event is a victim event
    or disclosure event.
    """

    if is_disclosure_event(event):

        details = event.get(
            "details",
            {}
        )

        announcement_id = details.get(
            "announcement_id"
        )

        current_disclosure = (
            get_disclosure_observation(
                event.get(
                    "observation_id"
                )
            )
        )

        previous_disclosure = (
            get_disclosure_observation(
                event.get(
                    "previous_observation_id"
                )
            )
        )

        announcement_observation = (
            get_announcement_observation(
                announcement_id
            )
        )

        return {
            "current_observation": current_disclosure,
            "previous_observation": previous_disclosure,
            "organization_observation": (
                announcement_observation
            ),
        }

    source_name = event.get("source") or SOURCE_NAME
    current_observation = get_observation(
        event.get("observation_id"), source_name=source_name
    )

    previous_observation = get_observation(
        event.get("previous_observation_id"), source_name=source_name
    )

    return {
        "current_observation": current_observation,
        "previous_observation": previous_observation,
        "organization_observation": (
            current_observation
        ),
    }


def get_description(
    observation: dict | None,
):

    if not observation:
        return []

    return observation.get(
        "descriptions",
        []
    )


@router.get("")
def get_changes(
    limit: int = 50,
    group: str | None = None,
    range: str | None = None,
):

    """
    Return recent intelligence changes for the
    Changes table.
    """

    # The Changes view needs to include every event in the current database;
    # cap pathological requests while allowing the normal dashboard history.
    limit = min(max(limit, 1), 5000)

    benchmark = get_event_benchmark()
    now = datetime.now(timezone.utc)
    if range is None:
        discovery_cutoff = max(now - timedelta(hours=48), benchmark)
        changes_cutoff = benchmark
    else:
        if range.casefold() == "all":
            range_cutoff = benchmark
        else:
            try:
                days = int(range)
            except (TypeError, ValueError):
                days = 30
            range_cutoff = max(now - timedelta(days=1 if days == 1 else days), benchmark)
        discovery_cutoff = changes_cutoff = benchmark
    query = {
        "$or": [
            {
                "event_type": "VICTIM_DISCOVERED",
                "detected_at": {"$gte": discovery_cutoff},
            },
            {
                "event_type": {"$ne": "VICTIM_DISCOVERED"},
                "detected_at": {"$gte": changes_cutoff},
            },
        ],
    }
    source_slugs = source_slugs_for_group(group)
    if source_slugs is not None:
        query["source"] = {"$in": source_slugs}

    # Leak dates live on the linked observation, so Mongo cannot sort events
    # by source date before resolving their observation context.
    documents = events.find(query).sort([("detected_at", -1), ("_id", -1)])

    results = []

    for event in documents:

        context = resolve_event_context(
            event
        )

        current_observation = (
            context[
                "current_observation"
            ]
        )

        if (
            event.get("source") in SOURCE_DATE_GATED_DISCOVERIES
            and event.get("event_type") == "VICTIM_DISCOVERED"
            and not has_recent_source_date((current_observation or {}).get("leak_at"), now)
        ):
            continue

        organization_observation = (
            context[
                "organization_observation"
            ]
        )

        source_name = event.get("source") or SOURCE_NAME
        ransomware_group = get_ransomware_group(source_name)
        if (ransomware_group or "").casefold() == "kazu":
            # Kazu's original discovery event predates flag normalization.
            # Read the latest corrected snapshot so the Changes table gets the
            # ISO country code without rewriting historical evidence.
            latest_kazu_observation = observations.find_one(
                {"source": source_name, "source_id": event.get("source_id")},
                sort=[("observed_at", -1)],
            )
            if latest_kazu_observation:
                organization_observation = latest_kazu_observation

        organization = get_organization(
            organization_observation
        )

        organization_id = (
            organization.get("id")
            if organization
            else (
                organization_observation.get(
                    "company_id"
                )
                if organization_observation
                else None
            )
        )

        event_type = event.get(
            "event_type"
        )
        changes = event.get(
            "changes",
            {}
        )
        display_event_type = event_type
        descriptions_change = changes.get("descriptions") if isinstance(changes, dict) else None
        if (
            event_type == "DESCRIPTION_CHANGED"
            and isinstance(descriptions_change, dict)
            and _text_indicates_disclosure(descriptions_change.get("current"))
            and not _text_indicates_disclosure(descriptions_change.get("previous"))
        ):
            # A number of non-INC sources announce publication in the victim
            # description rather than in a separate disclosure endpoint.
            display_event_type = "DISCLOSURE_DISCOVERED"
        elif event_type == "VICTIM_DISCOVERED":
            current_status = str((current_observation or {}).get("source_publication_status") or "").casefold()
            if current_status in {"published", "disclosed", "leaked", "public", "exposed"} or _text_indicates_disclosure((current_observation or {}).get("descriptions", [])):
                # Some collectors first encounter a victim after publication;
                # present the first-seen record with its explicit disclosure state.
                display_event_type = "VICTIM_DISCOVERED_AND_DISCLOSED"

        source_metadata_date = _source_metadata_date(organization_observation)
        # Some sources expose estimated publication deadlines through a field
        # normalized as leak_at. A future date is not a leak date yet; omit it
        # from the Changes feed so it cannot outrank other groups' real events.
        if _date_timestamp(source_metadata_date) > now.timestamp():
            source_metadata_date = None

        result = {
                "event_id": str(
                    event["_id"]
                ),

                "source_id": event.get(
                    "source_id"
                ),

                "collection_run_id": event.get(
                    "collection_run_id"
                ),

                "event_type": display_event_type,

                "detected_at": event.get(
                    "detected_at"
                ),

                # leak_at is normalized from each site's listed/published date
                # into the shared observation model.
                "leak_date": source_metadata_date,
                "published_at": source_metadata_date,

                "organization": (
                    display_organization_name(organization.get("name"), ransomware_group)
                    if organization
                    else (
                        display_organization_name(
                            organization_observation.get("company_name"), ransomware_group
                        )
                        if organization_observation
                        else "Unknown"
                    )
                ),

                # Added for Changes table country flag
                "country": (
                    organization_observation.get(
                        "country"
                    )
                    if organization_observation
                    else None
                ),

                "domains": get_domains(
                    organization_id
                ),

                "description": get_description(
                    organization_observation
                ),

                "ransomware_group": (
                    ransomware_group
                ),

                "change_description": (
                    build_change_description(
                        display_event_type,
                        changes,
                        current_observation,
                        event.get("detected_at"),
                    )
                ),

                "changed_fields": event.get(
                    "changed_fields",
                    []
                ),

                "changes": changes,

                "observation_id": event.get(
                    "observation_id"
                ),

                "previous_observation_id": (
                    event.get(
                        "previous_observation_id"
                    )
                ),
            }
        if range is not None:
            metadata_date = result.get("leak_date") or result.get("published_at")
            effective_date = _date_timestamp(metadata_date) or _date_timestamp(result.get("detected_at"))
            if effective_date < range_cutoff.timestamp():
                continue
        results.append(result)

    # A newly listed INC victim can arrive with its disclosure snapshot in
    # the same collection cycle. The event store correctly keeps both facts,
    # but presenting them as two adjacent rows looks like a duplicate victim.
    # Coalesce that specific pair for the Changes feed while retaining both
    # source events and linking the combined row to the disclosure evidence.
    discovered_keys = {
        (item.get("source_id"), item.get("ransomware_group"), item.get("collection_run_id"))
        for item in results
        if item.get("event_type") == "VICTIM_DISCOVERED"
    }
    disclosure_keys = {
        (item.get("source_id"), item.get("ransomware_group"), item.get("collection_run_id"))
        for item in results
        if item.get("event_type") == "DISCLOSURE_DISCOVERED"
    }
    paired_keys = discovered_keys & disclosure_keys
    if paired_keys:
        coalesced = []
        for item in results:
            key = (item.get("source_id"), item.get("ransomware_group"), item.get("collection_run_id"))
            if key in paired_keys and item.get("event_type") == "VICTIM_DISCOVERED":
                continue
            if key in paired_keys and item.get("event_type") == "DISCLOSURE_DISCOVERED":
                item = {
                    **item,
                    "event_type": "VICTIM_DISCOVERED_AND_DISCLOSED",
                }
            coalesced.append(item)
        results = coalesced

    results.sort(
        key=lambda item: (
            _date_timestamp(item.get("leak_date"))
            or _date_timestamp(item.get("detected_at")),
            _date_timestamp(item.get("detected_at")),
            item.get("event_id", ""),
        ),
        reverse=True,
    )
    return results[:limit]


@router.get("/{event_id}")
def get_change_details(
    event_id: str,
):

    """
    Return the complete forensic context for
    a single change event.
    """

    object_id = get_object_id(
        event_id
    )

    if not object_id:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    event = events.find_one(
        {"_id": object_id}
    )

    if not event:

        raise HTTPException(
            status_code=404,
            detail="Change event not found",
        )

    context = resolve_event_context(
        event
    )

    current_observation = (
        context[
            "current_observation"
        ]
    )

    previous_observation = (
        context[
            "previous_observation"
        ]
    )

    organization_observation = (
        context[
            "organization_observation"
        ]
    )

    organization = get_organization(
        organization_observation
    )

    organization_id = (
        organization.get("id")
        if organization
        else (
            organization_observation.get(
                "company_id"
            )
            if organization_observation
            else None
        )
    )

    current_raw_evidence = None
    previous_raw_evidence = None

    if current_observation:

        current_raw_evidence = (
            get_raw_evidence(
                current_observation.get(
                    "raw_evidence_id"
                )
            )
        )

    if previous_observation:

        previous_raw_evidence = (
            get_raw_evidence(
                previous_observation.get(
                    "raw_evidence_id"
                )
            )
        )

    return {
        "event": {
            "event_id": str(
                event["_id"]
            ),

            "source": event.get(
                "source"
            ),

            "source_id": event.get(
                "source_id"
            ),

            "collection_run_id": event.get(
                "collection_run_id"
            ),

            "event_type": event.get(
                "event_type"
            ),

            "detected_at": event.get(
                "detected_at"
            ),

            "changed_fields": event.get(
                "changed_fields",
                []
            ),

            "changes": event.get(
                "changes",
                {}
            ),

            "details": event.get(
                "details",
                {}
            ),
        },

        "organization": (
            organization
            if organization
            else {
                "name": (
                    organization_observation.get(
                        "company_name"
                    )
                    if organization_observation
                    else None
                ),

                "id": (
                    organization_observation.get(
                        "company_id"
                    )
                    if organization_observation
                    else None
                ),
            }
        ),

        "country": (
            organization_observation.get("country")
            if organization_observation
            else None
        ),

        "domains": get_domains(
            organization_id
        ),

        "ransomware_group": get_ransomware_group(event.get("source") or SOURCE_NAME),

        "previous_snapshot": clean_document(
            previous_observation
        ),

        "current_snapshot": clean_document(
            current_observation
        ),

        "previous_raw_evidence": clean_evidence_with_screenshot(previous_raw_evidence),

        "current_raw_evidence": clean_evidence_with_screenshot(current_raw_evidence),

        "organization_observation": (
            clean_document(
                organization_observation
            )
        ),
    }
