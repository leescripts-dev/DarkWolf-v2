from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from app.db.mongodb import db
from app.db.collection_state import get_event_benchmark
from app.entities.source_groups import (
    active_source_count,
    list_ransomware_groups,
    source_slugs_for_group,
)


router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)


organizations = db["organizations"]
countries = db["countries"]
events = db["events"]
sources = db["sources"]
observations = db["observations"]


def _range_cutoff(range_value: str, now: datetime) -> datetime | None:
    if range_value == "all":
        return None
    try:
        days = int(range_value)
    except (TypeError, ValueError):
        days = 30
    return now - timedelta(days=1 if days == 1 else days)


def _latest_observations(source_slugs: list[str] | None, cutoff: datetime | None = None):
    eligible_undated = None
    if cutoff is not None:
        benchmark = get_event_benchmark()
        discovery_query = {
            "event_type": "VICTIM_DISCOVERED",
            "detected_at": {"$gte": max(cutoff, benchmark)},
        }
        if source_slugs is not None:
            discovery_query["source"] = {"$in": source_slugs}
        eligible_undated = {
            (event.get("source"), event.get("source_id"))
            for event in events.find(discovery_query, {"source": 1, "source_id": 1})
            if event.get("source") and event.get("source_id")
        }

    query = {"source_id": {"$ne": None}}
    if source_slugs is not None:
        query["source"] = {"$in": source_slugs}
    latest = {}
    for item in observations.find(query).sort("observed_at", -1):
        identity = (item.get("source"), item.get("source_id"))
        if identity in latest:
            continue
        timestamp = item.get("leak_at")
        if cutoff is not None and timestamp:
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if timestamp < cutoff:
                continue
        elif cutoff is not None and identity not in eligible_undated:
            continue
        latest[identity] = item
    return latest.values()

# Country fields come from scraped sites and are not consistently formatted:
# some use ISO codes, some use names, and some append a state/city.
COUNTRY_CODES = {
    "usa": "US", "us": "US", "united states": "US", "united states of america": "US",
    "uk": "GB", "gb": "GB", "england": "GB", "great britain": "GB", "united kingdom": "GB",
    "uae": "AE", "united arab emirates": "AE", "northern macedonia": "MK",
    "thailand": "TH", "pakistan": "PK", "iran": "IR", "argentina": "AR",
    "turkey": "TR", "türkiye": "TR", "italy": "IT", "spain": "ES", "vietnam": "VN",
    "indonesia": "ID", "brazil": "BR", "austria": "AT", "armenia": "AM", "mexico": "MX",
    "panama": "PA", "ghana": "GH", "serbia": "RS", "peru": "PE", "saudi arabia": "SA",
    "egypt": "EG", "kenya": "KE", "malaysia": "MY", "seychelles": "SC", "slovakia": "SK",
    "morocco": "MA", "philippines": "PH", "canada": "CA", "belgium": "BE", "palestine": "PS",
    "chile": "CL", "bangladesh": "BD", "sudan": "SD", "moldova": "MD", "france": "FR",
    "india": "IN", "portugal": "PT", "malta": "MT", "south africa": "ZA",
    "dominican republic": "DO", "bolivia": "BO", "paraguay": "PY", "poland": "PL",
    "romania": "RO", "croatia": "HR", "switzerland": "CH", "germany": "DE",
    "australia": "AU", "czech republic": "CZ", "czechia": "CZ", "china": "CN",
    "japan": "JP", "russia": "RU", "ukraine": "UA", "israel": "IL", "south korea": "KR",
    "netherlands": "NL", "ireland": "IE", "sweden": "SE", "norway": "NO", "denmark": "DK",
    "finland": "FI", "singapore": "SG", "hong kong": "HK", "new zealand": "NZ",
}

COUNTRY_NAMES = {
    "US": "United States", "GB": "United Kingdom", "AE": "United Arab Emirates",
    "MK": "North Macedonia", "IR": "Iran", "TR": "Turkey", "PS": "Palestine",
    "MD": "Moldova", "CZ": "Czechia", "KR": "South Korea", "RU": "Russia",
    "CA": "Canada", "AU": "Australia", "FR": "France", "BR": "Brazil",
    "TW": "Taiwan",
}


def canonical_country(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    # Country is the first element on records formatted like "USA, Ohio" or
    # "MY, ID, TH". Assign one primary country so one victim counts once.
    parts = [part.strip().casefold() for part in value.split(",") if part.strip()]
    for part in parts:
        code = COUNTRY_CODES.get(part)
        if not code and len(part) == 2 and part.isalpha():
            code = part.upper()
        if code:
            return code, COUNTRY_NAMES.get(code, part.title())
    return None
@router.get("/groups")
def get_ransomware_groups():
    return list_ransomware_groups()


@router.get("/countries")
def get_country_distribution(group: str | None = None, range: str = "30"):
    now = datetime.now(timezone.utc)
    cutoff = _range_cutoff(range, now)
    source_slugs = source_slugs_for_group(group)
    counts: dict[str, dict] = {}
    for observation in _latest_observations(source_slugs, cutoff):
        canonical = canonical_country(observation.get("country"))
        if canonical is None:
            continue
        code, label = canonical
        if code not in counts:
            counts[code] = {
                "country": label,
                "normalized_name": label.casefold(),
                "country_code": code,
                "count": 0,
            }
        counts[code]["count"] += 1

    return sorted(counts.values(), key=lambda item: (-item["count"], item["country"]))


@router.get("/metrics")
def get_dashboard_metrics(range: str = "30", group: str | None = None):
    # ---------------------------------------------------------
    # Current time
    # ---------------------------------------------------------

    now = datetime.now(timezone.utc)

    # ---------------------------------------------------------
    source_slugs = source_slugs_for_group(group)
    cutoff = _range_cutoff(range, now)
    total_victims = sum(1 for _ in _latest_observations(source_slugs, cutoff))

    # ---------------------------------------------------------
    # New victims
    #
    # New victim events are counted inside the selected range and after the
    # active collection baseline.
    # ---------------------------------------------------------

    new_victims_query = {
        "event_type": "VICTIM_DISCOVERED",
    }

    # ---------------------------------------------------------
    # Changes detected
    #
    # VICTIM_DISCOVERED is excluded because it is already
    # represented by the New Victims KPI.
    # ---------------------------------------------------------

    changes_query = {
        "event_type": {
            "$ne": "VICTIM_DISCOVERED",
        },
    }
    if source_slugs is not None:
        new_victims_query["source"] = {"$in": source_slugs}
        changes_query["source"] = {"$in": source_slugs}

    # ---------------------------------------------------------
    # Apply selected time range
    #
    # range = 1   -> Last 24 Hours
    # range = 7   -> Last 7 Days
    # range = 30  -> Last 30 Days
    # range = 90  -> Last 90 Days
    # range = all -> All Time
    # ---------------------------------------------------------

    # Ignore legacy event history before the collection benchmark. The first
    # scraper run after rollout establishes this timestamp.
    benchmark = get_event_benchmark()
    new_victims_query["detected_at"] = {"$gte": max(cutoff or benchmark, benchmark)}
    changes_query["detected_at"] = {"$gte": benchmark}

    if cutoff is not None:
        changes_query["detected_at"]["$gte"] = max(cutoff, benchmark)

    # ---------------------------------------------------------
    # Execute queries
    # ---------------------------------------------------------

    new_victims = events.count_documents(
        new_victims_query
    )

    changes_detected = events.count_documents(
        changes_query
    )

    # ---------------------------------------------------------
    # Active sources
    #
    # Represents currently configured sources.
    # Not affected by the selected time range.
    # ---------------------------------------------------------

    active_sources = active_source_count(group)

    return {
        "total_victims": total_victims,
        "new_victims": new_victims,
        "changes_detected": changes_detected,
        "active_sources": active_sources,
    }
