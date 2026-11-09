"""Settra's rendered public leak listing and its in-page Load More control."""

from __future__ import annotations

import hashlib
import html
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait

from app.sites.html_leak_sites.collector import _screenshot
from app.sites.javascript_leak_sites.registry import JavascriptLeakSite


TOR_BROWSER_BINARY = r"C:\Users\USER\Desktop\Tor Browser\Browser\firefox.exe"
GECKODRIVER_PATH = r"C:\GekkoDriver\geckodriver.exe"
SETTRA_READY_TIMEOUT_SECONDS = 150
SETTRA_MAX_LISTING_CHUNKS = 12
CARD_SELECTOR = "a[href^='/leaks/']"


def _integer(value: str | None) -> int | None:
    digits = re.sub(r"[^0-9]", "", value or "")
    return int(digits) if digits else None


def _make_driver(tor_host: str, tor_port: int):
    options = webdriver.FirefoxOptions()
    options.binary_location = TOR_BROWSER_BINARY
    options.add_argument("-headless")
    options.set_preference("network.proxy.type", 1)
    options.set_preference("network.proxy.socks", tor_host)
    options.set_preference("network.proxy.socks_port", tor_port)
    options.set_preference("network.proxy.socks_remote_dns", True)
    options.set_preference("network.proxy.socks_version", 5)
    # Selenium creates a temporary browser profile for this run. The challenge
    # session is used only in-memory and is discarded when Firefox exits.
    return webdriver.Firefox(service=Service(GECKODRIVER_PATH), options=options)


def _card_record(card: dict, captured_at: datetime) -> dict | None:
    href = str(card.get("href") or "")
    domain = str(card.get("name") or "").strip().casefold().removeprefix("www.")
    description = html.unescape(re.sub(r"\s+", " ", str(card.get("description") or ""))).strip()
    if not href or not domain:
        return None

    # Settra's card heading is the domain. Its description starts with the
    # organization name, followed by narrative text; preserve the full snippet
    # and use the lead phrase as the display name when it is identifiable.
    lead = re.split(
        r"\s+(?:PROLOGUE\b|Documents?\s*:|Inside\s*:|A (?:holding )?company\b|The company\b|Employees\s+Under\s+NDA\b)",
        description,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" .:-")
    lead = re.sub(r"^Documents?\s*:\s*", "", lead, flags=re.I).strip()
    lead = re.sub(r"^BORROWED\s+IMAGE\s+", "", lead, flags=re.I).strip()
    if ":" in lead:
        lead = lead.split(":", 1)[0].strip()
    if len(lead) > 80 or re.match(r"^(?:A\s+|How\s+|\")", lead, re.I):
        lead = domain
    organization = lead if 2 <= len(lead) <= 80 else domain

    status_text = str(card.get("status") or "").casefold()
    source_status = "published" if "published" in status_text else None
    timer_raw = " ".join(status_text.split())
    if "until publish" in status_text:
        source_status = "yet_to_publish"
        timer = re.search(r"(?:(\d+)\s*d\s*)?(?:(\d+)\s*h\s*)?(?:(\d+)\s*m\s*)?(\d+)\s*s\b", status_text)
        colon_timer = re.search(r"(?:(\d+)\s*d\s*)?(\d{1,2}):(\d{2}):(\d{2})", status_text)
        if timer:
            days, hours, minutes, seconds = (int(value or 0) for value in timer.groups())
            remaining = days * 86400 + hours * 3600 + minutes * 60 + seconds
            deadline = captured_at + timedelta(seconds=remaining) if remaining > 0 else None
        elif colon_timer:
            days, hours, minutes, seconds = (int(value or 0) for value in colon_timer.groups())
            remaining = days * 86400 + hours * 3600 + minutes * 60 + seconds
            deadline = captured_at + timedelta(seconds=remaining) if remaining > 0 else None
        else:
            remaining = None
            deadline = None
    else:
        remaining = None
        deadline = None

    listed_date = card.get("date")
    details = []
    size = card.get("size")
    revenue = card.get("revenue")
    if size:
        details.append(f"Leak size: {size}")
    if revenue:
        details.append(f"Reported revenue: {revenue}")
    if description:
        details.append(description)

    return {
        "source_record_id": href.rstrip("/").rsplit("/", 1)[-1],
        "organization": organization,
        "country": None,
        "listed_date": listed_date,
        "domain": domain if "." in domain else None,
        "website": f"https://{domain}" if "." in domain else None,
        "categories": [],
        "descriptions": details,
        "visits": _integer(card.get("views")),
        "source_publication_status": source_status,
        "estimated_publish_at": deadline.isoformat() if deadline else None,
        "countdown_captured_at": captured_at.isoformat() if remaining is not None else None,
        "countdown_seconds_at_capture": remaining,
        "countdown_raw": timer_raw if remaining is not None else None,
    }


def collect_settra(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    """Wait for Settra's browser-side verification, then collect list cards.

    No verification request is forged or emulated. Firefox runs the page's own
    JavaScript challenge in the normal browser context. Only listing fields are
    read; detail pages and leak/download links are not opened.
    """
    driver = None
    errors: list[str] = []
    pages: list[dict] = []
    seen_hrefs: set[str] = set()
    visited_chunks = 0
    try:
        driver = _make_driver(tor_host, tor_port)
        driver.set_page_load_timeout(180)
        driver.set_script_timeout(45)
        listing_url = site.url.rstrip("/") + "/leaks"
        try:
            driver.get(listing_url)
        except TimeoutException:
            errors.append("initial navigation exceeded 180s; waiting for the rendered listing")

        try:
            WebDriverWait(driver, SETTRA_READY_TIMEOUT_SECONDS).until(
                lambda browser: (
                    urlparse(browser.current_url).hostname == urlparse(site.url).hostname
                    and browser.title.casefold() != "loading"
                    and bool(browser.find_elements("css selector", CARD_SELECTOR))
                )
            )
        except TimeoutException:
            title = (driver.title or "").strip()
            body = " ".join((driver.find_element("tag name", "body").text or "").split())[:500]
            errors.append(f"Settra listing did not render within {SETTRA_READY_TIMEOUT_SECONDS}s (title={title!r}; body={body!r})")
            return {"site": site, "pages": [], "pages_visited": 1, "errors": errors, "challenge": None}

        for chunk_number in range(1, SETTRA_MAX_LISTING_CHUNKS + 1):
            cards = driver.execute_script("""
              return [...document.querySelectorAll(arguments[0])].map(card => {
                const txt = node => (node?.innerText || '').replace(/\\s+/g,' ').trim();
                const valueFor = label => {
                  const node = [...card.querySelectorAll('div')].find(el => txt(el) === label && el.children.length === 0);
                  return node?.parentElement?.querySelector('div:last-child')?.innerText?.trim() || '';
                };
                const spans = [...card.querySelectorAll('span')].map(txt).filter(Boolean);
                const timeText = txt(card.querySelector('time,[class*="date"]'));
                const full = txt(card);
                const dateMatch = full.match(/\\b20\\d{2}-\\d{2}-\\d{2}\\b/);
                return {
                  href: card.getAttribute('href'),
                  name: txt(card.querySelector('h3')) || card.querySelector('img[alt]')?.getAttribute('alt') || '',
                  description: txt(card.querySelector('p')),
                  status: spans.join(' ') + ' ' + full.slice(0, 100),
                  date: dateMatch?.[0] || timeText || '',
                  size: valueFor('Size'), revenue: valueFor('Revenue'), views: valueFor('Views')
                };
              });
            """, CARD_SELECTOR)
            captured_at = datetime.now(timezone.utc)
            new_records = []
            for card in cards:
                href = str(card.get("href") or "")
                if not href or href in seen_hrefs:
                    continue
                seen_hrefs.add(href)
                record = _card_record(card, captured_at)
                if record:
                    new_records.append(record)

            screenshot, dimensions = _screenshot(driver)
            pages.append({
                "url": driver.current_url,
                "title": driver.title or site.name,
                "status_code": 200,
                "content_type": "text/html",
                "records": new_records,
                "screenshot": screenshot,
                "screenshot_sha256": hashlib.sha256(screenshot).hexdigest() if screenshot else None,
                "screenshot_dimensions": dimensions,
                "response_metadata": {"listing_chunk": chunk_number, "cumulative_cards": len(cards)},
            })
            visited_chunks += 1

            button = driver.find_elements(
                "xpath",
                "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'load more')]",
            )
            if not button or not button[0].is_displayed() or not button[0].is_enabled():
                break
            before = len(cards)
            button[0].click()
            try:
                WebDriverWait(driver, 35).until(
                    lambda browser: len(browser.find_elements("css selector", CARD_SELECTOR)) > before
                    or not browser.find_elements("xpath", "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'load more')]")
                )
            except TimeoutException:
                errors.append("Load More did not add listing cards; pagination stopped")
                break
            if len(driver.find_elements("css selector", CARD_SELECTOR)) <= before:
                break

        if not any(page.get("records") for page in pages) and not errors:
            errors.append("Settra rendered without any listing records")
    except (WebDriverException, OSError) as exc:
        errors.append(f"{type(exc).__name__}: {str(exc)[:350]}")
    finally:
        if driver:
            try:
                driver.quit()
            except WebDriverException:
                pass
    return {"site": site, "pages": pages, "pages_visited": visited_chunks, "errors": errors, "challenge": None}
