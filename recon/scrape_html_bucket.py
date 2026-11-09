"""Collect public listing metadata from the HTML-rendered leak-site bucket.

This intentionally does not open organization detail pages or download files.
It follows only pagination links and emits listing-level organization names,
dates, country labels, and source URLs when those fields are present.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent
INVENTORY = ROOT / "probe_results.json"
OUT = ROOT / "html_bucket_output.json"
REPORT = ROOT / "html_bucket_output.md"
TOR = "socks5h://127.0.0.1:9050"
PROXIES = {"http": TOR, "https": TOR}
TIMEOUT = 28
MAX_PAGES = 8
MAX_WORKERS = 3
UA = "Mozilla/5.0 (compatible; DarkWolfThreatResearch/1.0)"

# Fixed scope: the HTML-rendered bucket from the site-by-site reconnaissance.
HTML_BUCKET = {
    "APT73 (BASHE)", "ARCUS MEDIA", "BARRACUDA", "BLACKWATER", "Cinder",
    "CMD organization", "Daixin Ransomware", "DOOMMAGEDDON", "Emperador",
    "ENDZONE", "Falcon", "Global Secret Group", "Karma Leaks", "Kazu",
    "MS13-089 Blog", "SECP0", "ShadowByt3$", "Vexy",
}

# Explicit listing boundaries. Unknown layouts return zero records instead of
# guessing from arbitrary links or text on a page.
SITE_SELECTORS = {
    "APT73(BASHE)": "h2, h3, h4",
    "ARCUS MEDIA": "article",
    "BARRACUDA": "main .fish-eye-item",
    "BLACKWATER": ".card",
    "Cinder": "table tr",
    "CMD organization": ".item-card",
    "Daixin Ransomware": "h4.card-title",
    "DOOMMAGEDDON": "main h2",
    "Emperador": ".card",
    "ENDZONE": "h2.company-name",
    "Falcon": ".company-card, .entity-card",
    "Global Secret Group": ".card-title",
    "Karma Leaks": ".card",
    "Kazu": ".victim, .company, .post, article",
    "MS13-089 Blog": ".post",
    "SECP0": ".post",
    "ShadowByt3$": ".victim, .company, .post, article",
    "Vexy": "article, .card",
}

DATE_RE = re.compile(
    r"\b(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|"
    r"\d{1,2}[-/.]\d{1,2}[-/.]20\d{2}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},?\s+20\d{2})\b", re.I
)
COUNTRY_RE = re.compile(r"\b(?:country|location)\s*[:\-]\s*([\w .'-]{2,50})", re.I)
NEXT_RE = re.compile(r"^(?:next|older|›|»|→|>)$", re.I)


def same_origin(url: str, origin: str) -> bool:
    a, b = urlparse(url), urlparse(origin)
    return a.scheme in {"http", "https"} and a.netloc.lower() == b.netloc.lower()


def site_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def fetch(session: requests.Session, url: str) -> tuple[str, str, int]:
    response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    ctype = (response.headers.get("content-type") or "").lower()
    if "html" not in ctype and "xml" not in ctype and not response.text.lstrip().lower().startswith("<!doctype html"):
        raise ValueError(f"Expected HTML listing, got {ctype or 'unknown content type'}")
    return response.url, response.text, response.status_code


def clean_text(node: Tag) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def extract_items(soup: BeautifulSoup, site: dict, page_url: str) -> list[dict]:
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()
    name = site["name"]
    selector = SITE_SELECTORS.get(name)
    if not selector:
        return records
    for node in soup.select(selector):
        text = clean_text(node)
        anchors = node.select("a[href]")
        if name == "Cinder":
            cells = node.find_all(["td", "th"], recursive=False)
            organization = clean_text(cells[-1]) if len(cells) >= 4 and cells[0].name == "td" else ""
            anchor = next((a for a in (cells[-1].select("a[href]") if cells else []) if clean_text(a)), None)
        elif name == "CMD organization":
            title = node.select_one(".item-header")
            organization = clean_text(title) if title else ""
            anchor = title.find("a", href=True) if title else None
        elif name in {"Daixin Ransomware", "Global Secret Group", "ENDZONE", "DOOMMAGEDDON", "APT73(BASHE)"}:
            organization = clean_text(node)
            anchor = node.find("a", href=True)
        else:
            title = node.select_one("h2,h3,h4,h5,.card-title,.company-name")
            if name == "SECP0" and title:
                organization = re.sub(r"^Leak:\s*", "", clean_text(title), flags=re.I)
            else:
                organization = clean_text(title) if title else ""
            anchor = title.find("a", href=True) if title else None
            anchor = anchor or (anchors[0] if anchors else None)
        if not organization or len(organization) < 2:
            continue
        normalized = organization.strip().lower().rstrip(":")
        if normalized in {"paid", "new", "important announcement", "about us", "read more", "see more", "download", "a little gift of exclusive data for everyone"}:
            continue
        # Cinder includes a header row. Daixin headings can include a country suffix.
        country = None
        if name == "Daixin Ransomware":
            country_match_name = re.search(r"\(([^()]*)\)\s*$", organization)
            if country_match_name and re.fullmatch(r"(?:[A-Z]{2,3})(?:\s*,\s*[A-Z]{2,3})*", country_match_name.group(1).strip()):
                country = country_match_name.group(1).strip()
                organization = organization[:country_match_name.start()].strip()
        time_node = node.find("time")
        date = (time_node.get("datetime") or clean_text(time_node)) if time_node else None
        if not date:
            match = DATE_RE.search(text)
            date = match.group(0) if match else None
        country_match = COUNTRY_RE.search(text)
        country = country or (country_match.group(1).strip() if country_match else None)
        key = (organization.casefold(), date or "")
        if key in seen:
            continue
        seen.add(key)
        records.append({
            "group": name,
            "organization": organization,
            "country": country,
            "listed_date": date,
            "listing_url": page_url,
            "record_type": "listing_metadata",
        })
    return records


def pagination_urls(soup: BeautifulSoup, current: str, origin: str) -> list[str]:
    candidates: list[str] = []
    pagination = soup.select("nav[aria-label*='pagination' i], .pagination, .page-numbers, .pager, [class*='pagination']")
    links = [a for box in pagination for a in box.select("a[href]")]
    links.extend(soup.select("a[rel~='next'][href]"))
    for a in links:
        href = (a.get("href") or "").strip()
        label = clean_text(a).lower()
        rel = " ".join(a.get("rel", [])).lower()
        classes = " ".join(a.get("class", [])).lower()
        parsed = urlparse(urljoin(current, href))
        query = parsed.query.lower()
        looks_page = "next" in rel or NEXT_RE.match(label) is not None or "next" in classes or (bool(pagination) and (label.isdigit() or "page" in classes))
        absolute = urljoin(current, href)
        if looks_page and absolute != current and same_origin(absolute, origin):
            candidates.append(absolute)
    return list(dict.fromkeys(candidates))


def scrape_site(site: dict) -> dict:
    session = requests.Session()
    session.proxies.update(PROXIES)
    session.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    start = site["final_url"] if site.get("final_url", "").startswith("http") else site["url"]
    origin = f"{urlparse(start).scheme}://{urlparse(start).netloc}"
    queue = [start]
    visited: set[str] = set()
    items: list[dict] = []
    errors: list[str] = []
    while queue and len(visited) < MAX_PAGES:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            final_url, html, status = fetch(session, url)
            soup = BeautifulSoup(html, "html.parser")
            # Stop on challenge interstitials rather than trying to work around them.
            page_text = clean_text(soup).lower()[:6000]
            if any(token in page_text for token in ("captcha", "verify you are human", "proof of work", "anubis")):
                errors.append("challenge page detected; stopped")
                break
            items.extend(extract_items(soup, site, final_url))
            for nxt in pagination_urls(soup, final_url, origin):
                if nxt not in visited and nxt not in queue and len(visited) + len(queue) < MAX_PAGES:
                    queue.append(nxt)
            if status != 200:
                errors.append(f"HTTP {status} at {final_url}")
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    # Deduplicate by group + org + URL while preserving discovery order.
    deduped: list[dict] = []
    keys: set[tuple] = set()
    for item in items:
        key = (item["group"], item["organization"].casefold(), item["listed_date"])
        if key not in keys:
            keys.add(key)
            deduped.append(item)
    return {
        "site": site["name"],
        "start_url": start,
        "pages_visited": len(visited),
        "records_found": len(deduped),
        "records": deduped,
        "errors": errors,
    }


def main() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    bucket_keys = {site_key(name) for name in HTML_BUCKET}
    selected = [s for s in inventory if site_key(s.get("name", "")) in bucket_keys and s.get("ok") and not s.get("captcha")]
    selected.sort(key=lambda s: s["name"].casefold())
    selected_names = {site_key(s["name"]) for s in selected}
    missing = sorted(name for name in HTML_BUCKET if site_key(name) not in selected_names)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scrape_site, site): site["name"] for site in selected}
        results = [future.result() for future in as_completed(futures)]
    results.sort(key=lambda r: r["site"].casefold())
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "HTML bucket; listing metadata only; no detail pages or leak files",
        "sites_expected": len(HTML_BUCKET),
        "sites_attempted": len(selected),
        "sites_missing_from_successful_inventory": missing,
        "total_records": sum(r["records_found"] for r in results),
        "sites": results,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# HTML bucket scrape results", "",
        f"Generated: {payload['generated_at']}",
        f"Sites attempted: {len(selected)}/{len(HTML_BUCKET)} | Listing records: {payload['total_records']}",
        "Scope: public organization listing metadata only. Detail pages and leak files were not opened or downloaded.", "",
        "A zero-record result means no organization entries matched the current HTML selector on pages reached; it does not prove the site has no listings.", "",
    ]
    for result in results:
        lines.extend([f"## {result['site']}", f"Pages visited: {result['pages_visited']} | Records: {result['records_found']}"])
        if result["records"]:
            lines.append("")
            for item in result["records"]:
                details = [f"Listed: {item['listed_date'] or 'not shown'}", f"Country: {item['country'] or 'not shown'}"]
                lines.append(f"- **{item['organization']}** — {'; '.join(details)}")
        else:
            lines.append("\n- No organization listing records were extracted from the pages reached.")
        if result["errors"]:
            lines.append("\nNotes: " + " | ".join(result["errors"]))
        lines.append("")
    if missing:
        lines.extend(["## Not attempted", ""] + [f"- {name}: no successful non-challenge inventory entry" for name in missing] + [""])
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Sites attempted: {len(selected)}/{len(HTML_BUCKET)}")
    print(f"Listing records extracted: {payload['total_records']}")
    print(f"JSON: {OUT}")
    print(f"Readable report: {REPORT}")
    for result in results:
        print(f"{result['site']}: {result['records_found']} record(s), {result['pages_visited']} page(s)" + (f"; {len(result['errors'])} issue(s)" if result["errors"] else ""))


if __name__ == "__main__":
    main()
