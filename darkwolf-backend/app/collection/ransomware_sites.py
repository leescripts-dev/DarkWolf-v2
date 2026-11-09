import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import settings
from app.db.events import save_event
from app.db.collection_state import (
    get_event_benchmark,
    has_source_baseline,
    mark_source_baseline,
)
from app.db.observations import collection as observations_collection
from app.db.observations import get_latest_observation, save_observation
from app.db.raw_evidence import save_raw_evidence
from app.db.screenshots import save_screenshot
from app.entities.mapper import build_entity_id, map_observation
from app.entities.repository import persist_mapped_entities, upsert_source
from app.events.detector import detect_events
from app.events.new_victim_policy import SOURCE_DATE_GATED_DISCOVERIES, has_recent_source_date
from app.models.event import ThreatEvent
from app.models.observation import Observation
from app.models.raw_evidence import RawEvidence
from app.entities.models import Source
from app.sites.html_leak_sites.collector import collect_site_pages
from app.sites.html_leak_sites.registry import HTML_LEAK_SITES, HtmlLeakSite
from app.snapshots.differ import compare_observations
from app.snapshots.hasher import calculate_content_hash


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _source_record_id(
    site: HtmlLeakSite,
    organization: str,
    source_record_id: str | None = None,
) -> str:
    digest = hashlib.sha256(
        f"{site.slug}:{source_record_id or _normalized(organization)}".encode("utf-8")
    ).hexdigest()
    return digest[:32]


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = re.sub(r"\s*\(views?:?[^)]*\)", "", value, flags=re.I).strip()
    cleaned = re.sub(r"\s+UTC\s*[+-]\s*\d+", "+00:00", cleaned, flags=re.I)
    candidates = [cleaned]
    date_match = re.search(r"\b\d{4}/\d{1,2}/\d{1,2}(?:\s+\d{1,2}:\d{2}:\d{2})?", cleaned)
    if date_match:
        candidates.insert(0, date_match.group(0))
    formats = (
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
        "%B %d, %Y at %I:%M %p UTC", "%b %d, %Y at %I:%M %p UTC",
    )
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
        for date_format in formats:
            try:
                parsed = datetime.strptime(candidate, date_format)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                continue
    return None


class RansomwareSitesCollectionService:
    """INC-style observation/change pipeline for the non-CAPTCHA HTML sites."""

    def __init__(
        self,
        sites=HTML_LEAK_SITES,
        collector=collect_site_pages,
        collection_source: str = "html_leak_sites",
    ):
        self.sites = sites
        self.collector = collector
        self.collection_source = collection_source

    def collect(self, baseline: bool = False) -> dict:
        run_id = str(uuid4())
        # Establish the UI history floor on the first collection after rollout.
        # Old event documents remain available as evidence, but are not shown as
        # current dashboard changes.
        get_event_benchmark()
        result = {
            "collection_run_id": run_id,
            "source": self.collection_source,
            "mode": "baseline" if baseline else "live",
            "sites_expected": len(self.sites),
            "sites_processed": 0,
            "pages_processed": 0,
            "organizations_found": 0,
            "observations_saved": 0,
            "first_observations": 0,
            "content_changed": 0,
            "unchanged": 0,
            "events_generated": 0,
            "screenshots_saved": 0,
            "markup_date_inspection": {
                "records_checked": 0,
                "records_with_markup_date": 0,
                "hidden_date_records": 0,
                "date_candidates_missing_from_extraction": 0,
                "hidden_date_missing_from_ui_records": 0,
                "dates_recovered_from_markup": 0,
                "by_site": {},
            },
            "errors": [],
        }

        for site in self.sites:
            source = Source(
                id=build_entity_id("source", site.slug),
                name=site.name,
                source_type="ransomware_leak_site",
                ransomware_group=site.name,
                url=site.url,
            )
            upsert_source(source)

        seen_records: set[tuple[str, str]] = set()

        for site in self.sites:
            try:
                collected = self.collector(
                    site,
                    tor_host=settings.tor_host,
                    tor_port=settings.tor_socks_port,
                )
                result["sites_processed"] += 1
                if collected.get("challenge"):
                    result["errors"].append({
                        "site": site.name,
                        "error": collected["challenge"],
                    })
                    continue
                result["errors"].extend(
                    {"site": site.name, "error": error}
                    for error in collected.get("errors", [])
                )

                site_pages = collected.get("pages", [])
                site_baseline = baseline or not has_source_baseline(site.slug)
                for page_number, page in enumerate(site_pages, start=1):
                    result["pages_processed"] += 1
                    records = page.get("records", [])
                    date_audit = (page.get("response_metadata") or {}).get("date_inspection") or {}
                    if date_audit:
                        site_audit = result["markup_date_inspection"]["by_site"].setdefault(site.slug, {
                            "records_checked": 0,
                            "records_with_markup_date": 0,
                            "hidden_date_records": 0,
                            "date_candidates_missing_from_extraction": 0,
                            "hidden_date_missing_from_ui_records": 0,
                            "dates_recovered_from_markup": 0,
                        })
                        for key in site_audit:
                            value = int(date_audit.get(key, 0) or 0)
                            site_audit[key] += value
                            result["markup_date_inspection"][key] += value
                    screenshot = page.get("screenshot", b"")
                    screenshot_id = None
                    if screenshot:
                        screenshot_id = save_screenshot(
                            image=screenshot,
                            filename=f"{site.slug}-page-{page_number}-{run_id}.png",
                            metadata={
                                "source": site.slug,
                                "ransomware_group": site.name,
                                "collection_run_id": run_id,
                                "page_url": page["url"],
                                "captured_at": datetime.now(timezone.utc),
                                "sha256": page.get("screenshot_sha256"),
                                "dimensions": page.get("screenshot_dimensions", {}),
                            },
                        )
                        result["screenshots_saved"] += 1

                    evidence_body = {
                        "page_title": page.get("title"),
                        "page_url": page["url"],
                        "response_metadata": page.get("response_metadata", {}),
                        "records": records,
                    }
                    serialized = json.dumps(evidence_body, ensure_ascii=False, sort_keys=True, default=str)
                    evidence = RawEvidence(
                        source=site.slug,
                        source_id=f"listing-page:{page_number}",
                        collection_run_id=run_id,
                        endpoint=page["url"],
                        method="GET",
                        captured_at=datetime.now(timezone.utc),
                        status_code=page.get("status_code", 200),
                        content_type=page.get("content_type", "text/html"),
                        response_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
                        response_body=evidence_body,
                        metadata={
                            "type": f"{self.collection_source}_listing_page",
                            "ransomware_group": site.name,
                            "page_number": page_number,
                            "screenshot_id": screenshot_id,
                            "screenshot_sha256": page.get("screenshot_sha256"),
                            "screenshot_dimensions": page.get("screenshot_dimensions"),
                        },
                    )
                    evidence_id = save_raw_evidence(evidence)

                    for record in records:
                        organization_name = record.get("organization", "").strip()
                        if not organization_name:
                            continue
                        # Storm's companies API assigns a stable ID per listing;
                        # the same organization can legitimately have multiple
                        # distinct posts, so dedupe that source by record ID.
                        identity_value = (
                            str(record.get("source_record_id") or _normalized(organization_name))
                            if site.slug == "storm"
                            else _normalized(organization_name)
                        )
                        identity = (site.slug, identity_value)
                        if identity in seen_records:
                            continue
                        seen_records.add(identity)
                        source_id = _source_record_id(
                            site,
                            organization_name,
                            record.get("source_record_id"),
                        )
                        observation_time = datetime.now(timezone.utc)
                        company_id = build_entity_id(
                            "organization",
                            f"{site.slug}:{_normalized(organization_name)}",
                        )
                        previous = get_latest_observation(site.slug, source_id)
                        listed_at = _parse_date(record.get("listed_date"))
                        source_created_at = (
                            _parse_date(record.get("source_created_at"))
                            or (previous or {}).get("source_created_at")
                        )
                        storm_existing_org = False
                        if site.slug == "storm" and previous is None:
                            storm_existing_org = observations_collection.find_one(
                                {"source": site.slug, "company_name": organization_name},
                                {"_id": 1},
                            ) is not None
                        estimated_publish_at = _parse_date(record.get("estimated_publish_at"))
                        countdown_captured_at = _parse_date(record.get("countdown_captured_at"))
                        source_publication_status = (
                            record.get("source_publication_status")
                            or (previous or {}).get("source_publication_status")
                        )
                        # JavaScript pages can hide some attributes until a card
                        # expands. Keep previously observed values when the new
                        # rendered card does not expose that field.
                        domain = (
                            None
                            if record.get("clear_domain")
                            else record.get("domain") or (previous or {}).get("domain")
                        )
                        country = (
                            None
                            if record.get("clear_country")
                            else record.get("country") or (previous or {}).get("country")
                        )
                        categories = record.get("categories") or (previous or {}).get("categories") or []
                        descriptions = record.get("descriptions") or (previous or {}).get("descriptions") or []
                        leak_at = (
                            listed_at
                            if listed_at is not None or record.get("clear_leak_date")
                            else (previous or {}).get("leak_at")
                        )
                        preserve_countdown = bool(record.get("preserve_countdown_when_published"))
                        estimated_publish_at = (
                            None
                            if source_publication_status == "published" and not preserve_countdown
                            else estimated_publish_at or (previous or {}).get("estimated_publish_at")
                        )
                        countdown_captured_at = (
                            None
                            if source_publication_status == "published" and not preserve_countdown
                            else countdown_captured_at or (previous or {}).get("countdown_captured_at")
                        )
                        countdown_seconds_at_capture = (
                            None
                            if source_publication_status == "published" and not preserve_countdown
                            else record.get("countdown_seconds_at_capture")
                            if record.get("countdown_seconds_at_capture") is not None
                            else (previous or {}).get("countdown_seconds_at_capture")
                        )
                        countdown_raw = (
                            None
                            if source_publication_status == "published" and not preserve_countdown
                            else record.get("countdown_raw") or (previous or {}).get("countdown_raw")
                        )
                        observation_data = {
                            "company_name": organization_name,
                            "company_id": company_id,
                            "domain": domain,
                            "country": country,
                            "categories": categories,
                            "descriptions": descriptions,
                            "proof_ids": [],
                            "logo_id": None,
                            "leak_at": leak_at,
                            "source_created_at": source_created_at,
                            "estimated_publish_at": estimated_publish_at,
                            "countdown_captured_at": countdown_captured_at,
                            "countdown_seconds_at_capture": countdown_seconds_at_capture,
                            "countdown_raw": countdown_raw,
                            "source_publication_status": source_publication_status,
                            "cdn": None,
                        }
                        observation = Observation(
                            source=site.slug,
                            source_id=source_id,
                            collection_run_id=run_id,
                            raw_evidence_id=evidence_id,
                            source_display_name=site.name,
                            ransomware_group=site.name,
                            source_url=site.url,
                            listing_url=page["url"],
                            observed_at=observation_time,
                            company_name=organization_name,
                            company_id=company_id,
                            domain=domain,
                            country=country,
                            categories=categories,
                            descriptions=descriptions,
                            proof_ids=[],
                            visits=record.get("visits"),
                            leak_at=observation_data["leak_at"],
                            source_created_at=source_created_at,
                            estimated_publish_at=estimated_publish_at,
                            countdown_captured_at=countdown_captured_at,
                            countdown_seconds_at_capture=countdown_seconds_at_capture,
                            countdown_raw=countdown_raw,
                            source_publication_status=source_publication_status,
                            content_hash=calculate_content_hash(observation_data),
                        )
                        comparison = compare_observations(previous, observation.model_dump())
                        observation_id = save_observation(observation)
                        persist_mapped_entities(map_observation(observation))
                        result["organizations_found"] += 1
                        result["observations_saved"] += 1

                        change_type = comparison.get("change_type")
                        if change_type == "FIRST_OBSERVATION":
                            result["first_observations"] += 1
                        elif change_type == "CONTENT_CHANGED":
                            result["content_changed"] += 1
                        elif comparison.get("changed") is False:
                            result["unchanged"] += 1

                        if site_baseline:
                            continue
                        # Older Qilin scrapes treated the post/listing date as
                        # the leak date. Correcting that interpretation is a
                        # data repair, not a newly observed leak-date change.
                        if (
                            site.slug == "qilin"
                            and source_publication_status == "yet_to_publish"
                            and comparison.get("changed_fields") == ["leak_at"]
                        ):
                            continue
                        for event_data in detect_events(comparison):
                            if (
                                site.slug == "storm"
                                and storm_existing_org
                                and event_data.get("event_type") == "VICTIM_DISCOVERED"
                            ):
                                continue
                            if (
                                site.slug in SOURCE_DATE_GATED_DISCOVERIES
                                and event_data.get("event_type") == "VICTIM_DISCOVERED"
                                and not has_recent_source_date(leak_at, observation_time)
                            ):
                                continue
                            if (
                                site.slug == "qilin"
                                and event_data.get("event_type") == "LEAK_DATE_CHANGED"
                                and source_publication_status != "published"
                            ):
                                continue
                            event = ThreatEvent(
                                source=site.slug,
                                source_id=source_id,
                                collection_run_id=run_id,
                                event_type=event_data["event_type"],
                                detected_at=observation_time,
                                observation_id=observation_id,
                                previous_observation_id=str(previous["_id"]) if previous else None,
                                changed_fields=event_data["changed_fields"],
                                changes=event_data["changes"],
                                details={
                                    **event_data.get("details", {}),
                                    "listing_url": page["url"],
                                },
                            )
                            save_event(event)
                            result["events_generated"] += 1
                # A challenged/failed/empty response must not consume the
                # site's first-run baseline; its first successful scrape will.
                if site_pages and any(page.get("records") for page in site_pages) and not collected.get("errors"):
                    mark_source_baseline(site.slug, run_id, reset=baseline)
            except Exception as exc:
                result["errors"].append({"site": site.name, "error": str(exc)})

        return result
