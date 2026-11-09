"""Investigate HTML-bucket zero-result pages with headless Selenium over Tor.

Only public listing-level organization names, country/location labels, and dates
are emitted. The scraper never follows victim detail links or downloads files.
It detects and stops on CAPTCHA/proof-of-work pages without solving them.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parent
INVENTORY = ROOT / "recon" / "probe_results.json"
OUT = ROOT / "recon" / "html_bucket_browser_investigation.json"
REPORT = ROOT / "recon" / "html_bucket_browser_investigation.md"
TOR_PROXY = "socks5://127.0.0.1:9050"
PAGE_TIMEOUT_SECONDS = 75
RENDER_WAIT_SECONDS = 35
MAX_PAGES_PER_SITE = 10

TARGETS = {
    "APT73(BASHE)": "/",
    "BARRACUDA": "/leaks",
    "Cinder": "/",
    "Falcon": "/companies",
    "Karma Leaks": "/leaks",
    "Kazu": "/ransom.html",
    "MS13-089 Blog": "/",
    "ShadowByt3$": "/",
    "Vexy": "/blog",
}

CHALLENGE_MARKERS = (
    "captcha", "verify session", "verify your path", "verify you are human",
    "proof of work", "anubis", "turnstile", "ddos-guard", "checking your browser",
)


def make_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(f"--proxy-server={TOR_PROXY}")
    options.add_argument("--proxy-bypass-list=<-loopback>")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1440,1200")
    options.page_load_strategy = "eager"
    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    })
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(PAGE_TIMEOUT_SECONDS)
    driver.set_script_timeout(20)
    return driver


def text(el) -> str:
    return re.sub(r"\s+", " ", (el.text or "")).strip()


def challenge_state(driver) -> str | None:
    url = driver.current_url.lower()
    title = (driver.title or "").lower()
    body = " ".join(driver.find_elements("tag name", "body")[0].text.lower().split()) if driver.find_elements("tag name", "body") else ""
    haystack = f"{url} {title} {body[:12000]}"
    for marker in CHALLENGE_MARKERS:
        if marker in haystack:
            return f"challenge detected ({marker})"
    return None


def get_optional(element, selector: str) -> str | None:
    matches = element.find_elements("css selector", selector)
    return text(matches[0]) if matches and text(matches[0]) else None


def add_record(out: list[dict], group: str, organization: str | None, country: str | None, listed_date: str | None, listing_url: str) -> None:
    if not organization:
        return
    organization = re.sub(r"\s+", " ", organization).strip(" \t\r\n|:-")
    if len(organization) < 2 or organization.lower() in {"paid", "new", "victims", "entities", "leaked data", "read more"}:
        return
    row = {
        "group": group,
        "organization": organization,
        "country_or_location": country,
        "listed_date": listed_date,
        "listing_url": listing_url,
    }
    if row not in out:
        out.append(row)


def extract_page(driver, group: str) -> list[dict]:
    rows: list[dict] = []

    if group == "APT73(BASHE)":
        for card in driver.find_elements("css selector", ".segment"):
            add_record(rows, group, get_optional(card, ".segment__text__off"),
                       get_optional(card, ".segment__country__deadline"),
                       get_optional(card, ".segment__date__deadline, .segment__date"), driver.current_url)

    elif group == "Cinder":
        for tr in driver.find_elements("css selector", "table tr"):
            cells = tr.find_elements("css selector", "th,td")
            if len(cells) >= 4 and cells[0].tag_name.lower() == "td":
                add_record(rows, group, text(cells[-1]), None, None, driver.current_url)

    elif group == "Falcon":
        for card in driver.find_elements("css selector", ".leak-entry"):
            add_record(rows, group, get_optional(card, ".leak-company"),
                       get_optional(card, ".leak-country"),
                       get_optional(card, "time, .leak-date"), driver.current_url)

    elif group == "Karma Leaks":
        for card in driver.find_elements("css selector", ".card.card-compact"):
            add_record(rows, group, get_optional(card, "h3"),
                       get_optional(card, ".country, .card-country"),
                       get_optional(card, "[data-created-at], time, span"), driver.current_url)

    elif group == "MS13-089 Blog":
        for card in driver.find_elements("css selector", ".post"):
            title = get_optional(card, ".post-title-block > div:first-child")
            country = None
            match = re.search(r"\(([^()]*)\)\s*$", title or "")
            if match:
                country = match.group(1)
                title = (title or "")[:match.start()].strip()
            add_record(rows, group, title, country, get_optional(card, "time, .post-date"), driver.current_url)

    elif group == "Vexy":
        for title in driver.find_elements("css selector", ".company-name"):
            parent = title
            for _ in range(4):
                parents = parent.find_elements("xpath", "..")
                if not parents:
                    break
                parent = parents[0]
                if parent.find_elements("css selector", "time, .company-date, .date"):
                    break
            add_record(rows, group, text(title), get_optional(parent, ".country, .company-country"),
                       get_optional(parent, "time, .company-date, .date"), driver.current_url)

    elif group == "BARRACUDA":
        # The /leaks view uses list rows, while other routes show news and investigations.
        for card in driver.find_elements("css selector", ".grid .card"):
            heading = get_optional(card, "h3")
            add_record(rows, group, heading, get_optional(card, ".country"), get_optional(card, "time,.date"), driver.current_url)

    elif group == "Kazu":
        # Allow JS to render inline data into the DOM, but do not click any records.
        for item in driver.find_elements("css selector", "#productList li"):
            button = item.find_elements("css selector", "button.product-item")
            title = get_optional(item, ".product-item-title")
            date_text = text(button[0]) if button else text(item)
            date_match = re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2}\b", date_text, re.I)
            add_record(rows, group, title, None, date_match.group(0) if date_match else None, driver.current_url)
        for card in driver.find_elements("css selector", ".victim,.company,.item-card,.ransom-card,article"):
            heading = get_optional(card, "h2,h3,h4,.title,.company-name")
            add_record(rows, group, heading, get_optional(card, ".country,.location"), get_optional(card, "time,.date"), driver.current_url)

    return rows


def pagination_links(driver, origin: str) -> list[str]:
    boxes = driver.find_elements("css selector", "nav[aria-label*='pagination' i],.pagination,.pager,[class*='pagination']")
    links = [a for box in boxes for a in box.find_elements("css selector", "a[href]")]
    links += driver.find_elements("css selector", "a[rel~='next'][href]")
    found = []
    for link in links:
        href = link.get_attribute("href")
        if not href or urlparse(href).netloc.lower() != urlparse(origin).netloc.lower():
            continue
        label = (text(link) + " " + (link.get_attribute("rel") or "")).lower()
        if any(x in label for x in ("next", "older", "›", "»", "→")) or text(link).isdigit():
            found.append(href)
    return list(dict.fromkeys(found))


def inspect_site(driver, site: dict, path: str) -> dict:
    start = urljoin(site["final_url"], path)
    origin = f"{urlparse(start).scheme}://{urlparse(start).netloc}"
    queue, visited, records, issues = [start], set(), [], []
    blocked = None
    rendered = []
    while queue and len(visited) < MAX_PAGES_PER_SITE:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            try:
                driver.get(url)
            except TimeoutException:
                issues.append(f"page-load timeout after {PAGE_TIMEOUT_SECONDS}s: {url}")
            WebDriverWait(driver, RENDER_WAIT_SECONDS).until(
                lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
            )
            # Let deferred scripts and DOM mutations settle without infinite-scroll triggers.
            time.sleep(2)
            blocked = challenge_state(driver)
            if blocked:
                issues.append(blocked)
                break
            rendered.append({"url": driver.current_url, "title": driver.title,
                             "body_chars": len(driver.find_element("tag name", "body").text)})
            records.extend(extract_page(driver, site["name"]))
            for link in pagination_links(driver, origin):
                if link not in visited and link not in queue and len(visited) + len(queue) < MAX_PAGES_PER_SITE:
                    queue.append(link)
        except WebDriverException as exc:
            issues.append(f"browser error at {url}: {type(exc).__name__}: {str(exc)[:300]}")
            break
    # Deduplicate across pagination pages by group/name/date.
    unique, keys = [], set()
    for row in records:
        key = (row["group"], row["organization"].casefold(), row["listed_date"])
        if key not in keys:
            keys.add(key)
            unique.append(row)
    return {
        "site": site["name"], "start_url": start, "pages_visited": len(visited),
        "records_found": len(unique), "records": unique, "challenge_or_gate": blocked,
        "rendered_pages": rendered, "issues": issues,
    }


def main() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    by_key = {re.sub(r"[^a-z0-9]", "", item["name"].casefold()): item for item in inventory}
    results = []
    driver = make_driver()
    try:
        for name, path in TARGETS.items():
            key = re.sub(r"[^a-z0-9]", "", name.casefold())
            site = by_key.get(key)
            if not site:
                results.append({"site": name, "records_found": 0, "records": [], "issues": ["not found in saved recon inventory"]})
                continue
            results.append(inspect_site(driver, site, path))
    finally:
        driver.quit()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "browser": "Headless Chrome via Selenium; Tor SOCKS5 proxy",
        "scope": "Listing metadata only; no detail pages or leak files opened/downloaded; challenge pages are not solved",
        "page_load_timeout_seconds": PAGE_TIMEOUT_SECONDS,
        "sites_attempted": len(results),
        "total_records": sum(r.get("records_found", 0) for r in results),
        "sites": results,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Headless browser investigation: HTML sites with zero results", "",
             f"Generated: {payload['generated_at']}",
             f"Sites checked: {payload['sites_attempted']} | Listing records: {payload['total_records']}",
             f"Browser: {payload['browser']} | Page-load timeout: {PAGE_TIMEOUT_SECONDS}s", payload["scope"], ""]
    for result in results:
        lines.extend([f"## {result['site']}",
                      f"Pages visited: {result.get('pages_visited', 0)} | Records: {result.get('records_found', 0)}"])
        if result.get("challenge_or_gate"):
            lines.append(f"Gate: {result['challenge_or_gate']}; stopped at the interstitial.")
        if result.get("records"):
            lines.append("")
            for row in result["records"]:
                lines.append(f"- **{row['organization']}** — country/location: {row['country_or_location'] or 'not shown'}; listed: {row['listed_date'] or 'not shown'}")
        if result.get("rendered_pages"):
            lines.append("\nRendered page(s): " + "; ".join(f"{p['title']} ({p['body_chars']} text chars)" for p in result['rendered_pages']))
        if result.get("issues"):
            lines.append("\nIssues: " + " | ".join(result["issues"]))
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Sites checked: {len(results)} | Records: {payload['total_records']}")
    print(f"JSON: {OUT}\nReadable report: {REPORT}")
    for r in results:
        status = f"GATED: {r['challenge_or_gate']}" if r.get("challenge_or_gate") else f"{r.get('records_found', 0)} record(s)"
        print(f"{r['site']}: {status}; pages={r.get('pages_visited', 0)}" + (f"; issues={len(r['issues'])}" if r.get('issues') else ""))


if __name__ == "__main__":
    main()
