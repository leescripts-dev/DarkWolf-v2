from app.db.mongodb import db
from app.entities.mapper import build_entity_id
from app.sites.api_leak_sites.registry import API_LEAK_SITES
from app.sites.html_leak_sites.registry import HTML_LEAK_SITES
from app.sites.javascript_leak_sites.registry import JAVASCRIPT_LEAK_SITES


def configured_ransomware_sources() -> tuple[tuple[str, str], ...]:
    """Return sources in the scrape cycle plus the separately collected INC source."""
    sources = [
        (site.slug, site.name)
        for site in (*HTML_LEAK_SITES, *API_LEAK_SITES, *JAVASCRIPT_LEAK_SITES)
    ]
    sources.append(("inc_ransom", "Inc"))
    return tuple(sources)


def active_source_count(group: str | None = None) -> int:
    configured = configured_ransomware_sources()
    if not group or group.casefold() == "all":
        return len({slug for slug, _ in configured})
    return sum(1 for _, name in configured if name.casefold() == group.casefold())


def source_slugs_for_group(group: str | None) -> list[str] | None:
    """Resolve display group names to source slugs used by observations/events."""
    if not group or group.casefold() == "all":
        return None

    observations = db["observations"]
    sources = db["sources"]
    slugs = []
    for slug in observations.distinct("source"):
        source = sources.find_one(
            {"id": build_entity_id("source", slug)},
            {"_id": 0, "ransomware_group": 1},
        )
        if source and (source.get("ransomware_group") or "").casefold() == group.casefold():
            slugs.append(slug)
    return slugs


def list_ransomware_groups() -> list[str]:
    return sorted({name.strip() for _, name in configured_ransomware_sources()}, key=str.casefold)
