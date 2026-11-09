import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter

from app.db.mongodb import db
from app.entities.source_groups import configured_ransomware_sources
from app.sites.api_leak_sites.registry import API_LEAK_SITES
from app.sites.html_leak_sites.registry import HTML_LEAK_SITES
from app.sites.javascript_leak_sites.registry import JAVASCRIPT_LEAK_SITES
from app.sites.triage_registry import CAPTCHA_LEAK_SITES, MANUAL_INSPECTION_LEAK_SITES, UNAVAILABLE_LEAK_SITES


router = APIRouter(prefix="/api/v1/sources", tags=["Sources"])
INVENTORY_PATH = Path(__file__).resolve().parents[2] / "data" / "source_inventory.json"
REGISTERED_SITES = (*HTML_LEAK_SITES, *API_LEAK_SITES, *JAVASCRIPT_LEAK_SITES)


def _key(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _host(url: str | None) -> str:
    return (urlsplit(url or "").hostname or "").casefold()


def _last_scraped_by_source() -> dict[str, str]:
    slugs = [slug for slug, _ in configured_ransomware_sources()]
    latest: dict[str, str] = {}
    try:
        cursor = db["observations"].find(
            {"source": {"$in": slugs}},
            {"_id": 0, "source": 1, "observed_at": 1},
        ).sort("observed_at", -1)
        for item in cursor:
            source = item.get("source")
            timestamp = item.get("observed_at")
            if source and source not in latest and timestamp:
                if isinstance(timestamp, datetime):
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    latest[source] = timestamp.isoformat()
                else:
                    latest[source] = str(timestamp)
    except Exception:
        # Keep the inventory usable if Mongo is unavailable; timestamps render
        # as not recorded until the next successful request.
        return {}
    return latest


def _build_inventory() -> dict:
    snapshot = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    configured = configured_ransomware_sources()
    scraped_names = {_key(name) for _, name in configured}
    scraped_names.update({"interlock", "inc ransom", "qilin/agenda", "shadowbyt3$ / shadowbyt3s"})
    source_slug_by_name = {_key(site.name): site.slug for site in REGISTERED_SITES}
    source_slug_by_name[_key("Inc")] = "inc_ransom"
    source_slug_by_name[_key("Inc Ransom")] = "inc_ransom"
    scraped_hosts = set()
    for site in REGISTERED_SITES:
        scraped_hosts.add(_host(site.url))
        endpoint = getattr(site, "endpoint", None) or getattr(site, "api_url", None)
        if endpoint:
            scraped_hosts.add(_host(endpoint))

    captcha_names = {_key(site.name) for site in CAPTCHA_LEAK_SITES}
    captcha_hosts = {_host(site.url) for site in CAPTCHA_LEAK_SITES}
    manual_names = {_key(site.name) for site in MANUAL_INSPECTION_LEAK_SITES}
    unavailable_names = {_key(site.name) for site in UNAVAILABLE_LEAK_SITES}
    unavailable_hosts = {_host(site.url) for site in UNAVAILABLE_LEAK_SITES}
    last_scraped = _last_scraped_by_source()

    groups = []
    scraped_group_count = 0
    active_keys: set[str] = set()
    inaccessible_keys: set[str] = set()
    captcha_group_count = 0
    manual_group_count = 0

    for group in snapshot["groups"]:
        aliases = {_key(name) for name in group.get("aliases", [])}
        hosts = {_host(item.get("url")) for item in group.get("urls", [])}
        availability = [
            state
            for item in group.get("urls", [])
            for state in item.get("availability", [])
            if state
        ]
        is_scraped = bool(aliases & scraped_names or hosts & scraped_hosts)
        is_captcha = bool(aliases & captcha_names or hosts & captcha_hosts)
        is_manual = bool(aliases & manual_names)
        is_probe_active = any(
            state in {"active", "reachable_404", "reachable_server_error"}
            for state in availability
        )
        is_unreachable = bool(
            aliases & unavailable_names
            or hosts & unavailable_hosts
            or (availability and all(state == "unreachable_or_timeout" for state in availability))
        )

        matched_slugs = {source_slug_by_name[name] for name in aliases if name in source_slug_by_name}
        matched_slugs.update(
            site.slug
            for site in REGISTERED_SITES
            if _host(site.url) in hosts
        )
        scraped_at = next(
            (last_scraped[slug] for slug in sorted(matched_slugs) if slug in last_scraped),
            None,
        )
        recent_success = False
        if scraped_at:
            try:
                parsed_scraped_at = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
                if parsed_scraped_at.tzinfo is None:
                    parsed_scraped_at = parsed_scraped_at.replace(tzinfo=timezone.utc)
                recent_success = parsed_scraped_at >= datetime.now(timezone.utc) - timedelta(hours=48)
            except ValueError:
                recent_success = False

        if is_scraped:
            scraped_group_count += 1
        if is_captcha:
            captcha_group_count += 1
        if is_manual:
            manual_group_count += 1

        if is_captcha:
            # A verification page means the site responded; it is reachable,
            # even though automated scraping is blocked.
            status = "captcha"
            active_keys.add(group["key"])
        elif is_probe_active or recent_success:
            status = "scraped" if is_scraped else "active_not_scraped"
            active_keys.add(group["key"])
        elif is_unreachable and not is_probe_active:
            status = "inactive"
            inaccessible_keys.add(group["key"])
        elif is_scraped:
            status = "scraped"
            active_keys.add(group["key"])
        elif is_probe_active:
            status = "active_not_scraped"
            active_keys.add(group["key"])
        elif is_scraped:
            status = "scraped"
            active_keys.add(group["key"])
        elif is_manual:
            status = "manual_inspection"
        else:
            status = "not_checked"

        groups.append({
            **group,
            "status": status,
            "scraper_configured": is_scraped,
            "captcha_detected": is_captcha,
            "manual_inspection": is_manual,
            "last_probe_unreachable": is_unreachable,
            "last_scraped_at": scraped_at,
            "category": "Ransomware / data leak site",
        })

    # INC is collected by its dedicated pipeline and is not listed in the
    # workbook. Keep it in the configured scraper metric without inflating the
    # workbook's unique-group total.
    configured_count = len({slug for slug, _ in configured})
    total = len(groups)
    return {
        "inventory_name": snapshot["inventory_name"],
        "inventory_checked_at": snapshot["inventory_checked_at"],
        "summary": {
            "total_unique_groups": total,
            "active_sources": len(active_keys),
            "scraped_sources": configured_count,
            "not_scraped_sources": max(0, total - scraped_group_count),
            "captcha_sites": captcha_group_count,
            "inactive_sources": len(inaccessible_keys),
            "manual_inspection": manual_group_count,
            "scraped_groups_in_inventory": scraped_group_count,
            "unverified_sources": sum(1 for group in groups if group["status"] == "not_checked"),
        },
        "groups": groups,
    }


@router.get("")
def get_sources(status: str | None = None, search: str | None = None):
    inventory = _build_inventory()
    groups = inventory["groups"]
    if status and status != "all":
        if status == "not_scraped":
            groups = [group for group in groups if not group["scraper_configured"]]
        elif status == "inactive":
            groups = [group for group in groups if group["status"] == "inactive"]
        elif status == "active":
            groups = [group for group in groups if group["status"] in {"scraped", "captcha", "active_not_scraped"}]
        elif status == "captcha":
            groups = [group for group in groups if group["captcha_detected"]]
        elif status == "scraped":
            groups = [group for group in groups if group["scraper_configured"]]
        else:
            groups = [group for group in groups if group["status"] == status]
    if search:
        needle = search.casefold().strip()
        groups = [
            group for group in groups
            if needle in group["name"].casefold()
            or any(needle in item["url"].casefold() for item in group["urls"])
        ]
    inventory["groups"] = groups
    return inventory
