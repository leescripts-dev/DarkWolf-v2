import hashlib
import html
import json
import re
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait

from app.sites.html_leak_sites.collector import (
    MAX_PAGES_PER_SITE,
    _make_driver,
    _pagination_links,
    _screenshot,
)
from app.sites.javascript_leak_sites.registry import JavascriptLeakSite
from app.sites.javascript_leak_sites.blackx import collect_blackx
from app.sites.javascript_leak_sites.insomnia import collect_insomnia
from app.sites.javascript_leak_sites.storm import collect_storm
from app.sites.javascript_leak_sites.settra import collect_settra
from app.sites.markup_date_inspector import inspect_markup_dates


JS_PAGE_TIMEOUT_SECONDS = 25
SLOW_JS_SITE_PAGE_TIMEOUT_SECONDS = 90
SLOW_JS_SITE_SLUGS = {"atomsilo", "kairos", "leaknet", "lynx", "sovcali", "ulose", "storm"}
JS_RENDER_WAIT_SECONDS = 18
PLAY_MAX_PAGES = 40
LOCKBIT_QUEUE_TIMEOUT_SECONDS = 300


def _page_timeout_for_site(site: JavascriptLeakSite) -> int:
    return (
        SLOW_JS_SITE_PAGE_TIMEOUT_SECONDS
        if site.slug in SLOW_JS_SITE_SLUGS
        else JS_PAGE_TIMEOUT_SECONDS
    )


def _inertia_payload(soup: BeautifulSoup) -> dict | None:
    node = soup.select_one('script[data-page][type="application/json"]')
    if not node:
        return None
    try:
        payload = json.loads(node.string or node.get_text())
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _collect_everest_listing(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    """Read Everest's public Inertia category/post metadata, excluding post bodies and files."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    session = requests.Session()
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"})
    pages, errors = [], []
    try:
        root = session.get(site.url, timeout=(15, 45))
        root.raise_for_status()
        root_soup = BeautifulSoup(root.text, "html.parser")
        payload = _inertia_payload(root_soup)
        props = payload.get("props", {}) if payload else {}
        categories = props.get("categories") if isinstance(props, dict) else None
        if not isinstance(categories, list):
            raise ValueError("Everest page did not expose its Inertia category list")

        for category in categories:
            if not isinstance(category, dict) or not category.get("slug") or not category.get("title"):
                continue
            category_url = urljoin(site.url, f"news/{category['slug']}")
            posts, response = [], None
            try:
                response = session.get(category_url, timeout=(15, 45))
                response.raise_for_status()
                page_payload = _inertia_payload(BeautifulSoup(response.text, "html.parser"))
                page_props = page_payload.get("props", {}) if page_payload else {}
                post_rows = page_props.get("posts") if isinstance(page_props, dict) else None
                posts = post_rows if isinstance(post_rows, list) else []
            except (requests.RequestException, ValueError) as exc:
                errors.append(f"{category.get('title')}: {type(exc).__name__}: {str(exc)[:180]}")

            titles = [str(post.get("title") or "") for post in posts if isinstance(post, dict)]
            domain = None
            for title in titles:
                match = re.search(r"(?<![@\w])(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\b", title, re.I)
                if match:
                    domain = match.group(0).casefold().removeprefix("www.")
                    break
            timer_posts = [post for post in posts if isinstance(post, dict) and post.get("scheduled") and post.get("publishAt")]
            timer = timer_posts[0].get("publishAt") if timer_posts else None
            published = any(post.get("state") in {"open", "password"} for post in posts if isinstance(post, dict))
            status = "published" if published else "yet_to_publish" if timer else None
            captured_at = datetime.now(timezone.utc)
            deadline = None
            if isinstance(timer, str):
                try:
                    deadline = datetime.fromisoformat(timer.replace("Z", "+00:00"))
                    if deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=timezone.utc)
                    deadline = deadline.astimezone(timezone.utc)
                except ValueError:
                    deadline = None
            post_titles = [title.strip() for title in titles if title.strip()]
            record = {
                "source_record_id": str(category.get("id") or category["slug"]),
                "organization": re.sub(r"\s+", " ", str(category["title"])).strip(),
                "country": None,
                # Everest only exposes relative dates in this response. Do not
                # turn "yesterday" into a guessed leak timestamp.
                "listed_date": None,
                "domain": domain,
                "website": f"https://{domain}" if domain else None,
                "categories": [],
                "descriptions": post_titles[:3],
                "source_publication_status": status,
                "estimated_publish_at": deadline.isoformat() if deadline else None,
                "countdown_captured_at": captured_at.isoformat() if deadline else None,
                "countdown_seconds_at_capture": max(0, int((deadline - captured_at).total_seconds())) if deadline else None,
                "countdown_raw": timer,
                "preserve_countdown_when_published": bool(published and deadline),
                "source_date_label": category.get("date"),
            }
            pages.append({
                "url": response.url if response is not None else category_url,
                "title": str(category["title"]),
                "status_code": response.status_code if response is not None else root.status_code,
                "content_type": response.headers.get("content-type", "text/html") if response is not None else root.headers.get("content-type", "text/html"),
                "records": [record],
                "response_metadata": {"category_id": category.get("id"), "post_count": category.get("postCount"), "relative_date": category.get("date")},
                "screenshot": b"",
            })
            time.sleep(0.12)
    except (requests.RequestException, ValueError) as exc:
        errors.append(f"Everest listing failed: {type(exc).__name__}: {str(exc)[:300]}")
    finally:
        session.close()
    return {"site": site, "pages": pages, "pages_visited": len(pages) + (1 if pages else 0), "errors": errors, "challenge": None}


def _collect_exitium_listing(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    """Extract the public target-card metadata rendered in Exitium's HTML."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    try:
        response = requests.get(
            site.url,
            proxies={"http": proxy, "https": proxy},
            timeout=(45, 180),
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"Exitium listing failed: {type(exc).__name__}: {str(exc)[:300]}"], "challenge": None}

    soup = BeautifulSoup(response.text, "html.parser")
    records, seen = [], set()
    for card in soup.select(".target-card[data-id]"):
        name = re.sub(r"\s+", " ", card.get("data-title", "")).strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        text = html.unescape(card.get("data-text", ""))
        website_match = re.search(r"\bWebsite\s*:\s*(?:https?://)?([^\s/]+)", text, re.I)
        domain = website_match.group(1).casefold().removeprefix("www.").rstrip(".,;:") if website_match else None
        date = card.get("data-date")
        size_match = re.search(r"\bExfiltrated\s*:\s*([^\r\n]+)", text, re.I)
        records.append({
            "source_record_id": card.get("data-id") or name.casefold(),
            "organization": name,
            "country": None,
            "listed_date": date,
            "website": f"https://{domain}" if domain else None,
            "domain": domain,
            "categories": [],
            "descriptions": [f"Exfiltrated: {size_match.group(1).strip()}"] if size_match else [],
            "source_publication_status": "published",
        })
    errors = [] if records else ["no .target-card records found in Exitium HTML"]
    return {"site": site, "pages": [{
        "url": response.url, "title": soup.title.get_text(" ", strip=True) if soup.title else site.name,
        "status_code": response.status_code, "content_type": response.headers.get("content-type", "text/html"),
        "records": records, "screenshot": b"",
    }] if records else [], "pages_visited": 1, "errors": errors, "challenge": None}


def _collect_abyss_listing(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    """Read only the public title/short fields from Abyss' client-side list."""
    endpoint = urljoin(site.url, "static/data.js")
    proxy = f"socks5h://{tor_host}:{tor_port}"
    response = requests.get(
        endpoint,
        proxies={"http": proxy, "https": proxy},
        timeout=(15, 45),
        headers={"Accept": "application/javascript,text/plain,*/*"},
    )
    response.raise_for_status()
    pair_pattern = re.compile(
        r"['\"]title['\"]\s*:\s*'((?:\\.|[^'\\])*)'\s*,\s*"
        r"['\"]short['\"]\s*:\s*'((?:\\.|[^'\\])*)'",
        re.S,
    )
    records = []
    seen = set()
    for raw_title, raw_short in pair_pattern.findall(response.text):
        title = raw_title.replace("\\'", "'").replace("\\\\", "\\").strip()
        short = raw_short.replace("\\'", "'").replace("\\\\", "\\").strip()
        key = title.casefold()
        if len(title) < 2 or key in seen:
            continue
        seen.add(key)
        domain_match = re.search(
            r"(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
            short,
            re.I,
        )
        domain = domain_match.group(0).casefold().removeprefix("www.") if domain_match else None
        records.append({
            "source_record_id": key,
            "organization": title,
            "country": None,
            "listed_date": None,
            "website": f"https://{domain}" if domain else None,
            "domain": domain,
            "categories": [],
            "descriptions": [],
        })
    errors = [] if records else ["no title/short victim entries matched the public listing data"]
    return {
        "site": site,
        "pages": [{
            "url": endpoint,
            "title": "Abyss listing data",
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "application/javascript"),
            "records": records,
            "screenshot": b"",
        }] if records else [],
        "pages_visited": 1,
        "errors": errors,
        "challenge": None,
    }


def _collect_titan_listing(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    """TITAN serves its published listing as server-rendered HTML at /leaked."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    try:
        response = requests.get(
            site.url,
            proxies={"http": proxy, "https": proxy},
            timeout=(45, 180),
            headers={"Accept": "text/html,application/xhtml+xml,*/*"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"TITAN listing request failed: {type(exc).__name__}: {str(exc)[:300]}"],
                "challenge": None}

    soup = BeautifulSoup(response.text, "html.parser")
    records = []
    seen = set()
    for heading in soup.select("h1"):
        organization = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip()
        if organization.casefold() in {"leaked data", "awaiting publication"}:
            continue
        if len(organization) < 2 or organization.casefold() in seen:
            continue
        # Company names are h1s. The h2 in the same card is sometimes a status
        # or incident description, so it must not be used as the organization.
        card = heading.parent.parent if heading.parent and heading.parent.parent else heading.parent
        card_text = re.sub(r"\s+", " ", card.get_text(" ", strip=True) if card else "")
        ancestor = card
        while ancestor and ancestor.name not in {"body", "html"}:
            candidate_text = re.sub(r"\s+", " ", ancestor.get_text(" ", strip=True))
            if "Date of publication" in candidate_text and len(candidate_text) < 1800:
                card_text = candidate_text
                break
            ancestor = ancestor.parent
        domain_match = re.search(
            r"\bWebsite\s+([^\s]+)",
            card_text,
            re.I,
        )
        date_match = re.search(
            r"Date of publication\s+(.+?UTC)", card_text, re.I
        )
        domain = None
        if domain_match:
            website = domain_match.group(1).strip().rstrip(".,;)")
            host = urlparse(website if "://" in website else f"https://{website}").hostname
            excluded_hosts = {"linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com", "dunsguide.com"}
            if host and "." in host and not any(host.casefold() == excluded or host.casefold().endswith(f".{excluded}") for excluded in excluded_hosts):
                domain = host.casefold().removeprefix("www.")
        listed_date = date_match.group(1).strip() if date_match else None
        if not listed_date:
            # Do not silently import entries with an unknown date as if the
            # scrape time were their leak date.
            listed_date = None
        anchor = heading.find_parent("a")
        source_record_id = anchor.get("href") if anchor else None
        subtitle = card.select_one("h2") if card else None
        description = re.sub(r"\s+", " ", subtitle.get_text(" ", strip=True)) if subtitle else ""
        if description.casefold().startswith(organization.casefold()):
            description = description[len(organization):].strip(" .:-")
        if description.casefold() == organization.casefold():
            description = ""
        seen.add(organization.casefold())
        records.append({
            "source_record_id": source_record_id or domain or organization.casefold(),
            "organization": organization,
            "country": None,
            "listed_date": listed_date,
            "website": f"https://{domain}" if domain else None,
            "domain": domain,
            "categories": [],
            "descriptions": [description] if description else [],
            "source_publication_status": "published",
        })

    errors = [] if records else ["no TITAN victims found in the /leaked listing headings"]
    return {
        "site": site,
        "pages": [{
            "url": response.url,
            "title": soup.title.get_text(" ", strip=True) if soup.title else "TITAN Leaked Data",
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "text/html"),
            "records": records,
            "screenshot": b"",
        }] if records else [],
        "pages_visited": 1,
        "errors": errors,
        "challenge": None,
    }


def _collect_lockbit_listing(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    """Click through LockBit's public entry gate and wait for its access queue."""
    driver = _make_driver(tor_host, tor_port)
    driver.set_page_load_timeout(120)
    errors = []
    challenge = None
    records = []
    try:
        try:
            driver.get(site.url)
        except TimeoutException:
            errors.append("initial page load exceeded 120s")

        body = driver.find_element("tag name", "body").text
        if "click anywhere to enter" in body.casefold():
            entry = driver.find_elements("css selector", "a.btn")
            if not entry:
                return {"site": site, "pages": [], "pages_visited": 1,
                        "errors": ["entry prompt appeared without its expected link"], "challenge": None}
            entry[0].click()

        deadline = time.monotonic() + LOCKBIT_QUEUE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                cards = driver.find_elements("css selector", ".post-block")
                if cards:
                    break
                body = driver.find_element("tag name", "body").text
                challenge = _challenge(driver)
                if challenge:
                    errors.append(challenge)
                    break
                if "placed in a queue" not in body.casefold() and "access queue" not in driver.title.casefold():
                    # Give the frontend a brief chance to render after queue redirect.
                    time.sleep(2)
                    if driver.find_elements("css selector", ".post-block"):
                        break
            except WebDriverException as exc:
                errors.append(f"waiting for LockBit listing: {type(exc).__name__}: {str(exc)[:220]}")
                break
            time.sleep(3)
        else:
            errors.append(f"LockBit access queue exceeded {LOCKBIT_QUEUE_TIMEOUT_SECONDS}s")

        if not challenge:
            captured_at = datetime.now(timezone.utc)
            cards = driver.find_elements("css selector", ".post-block")
            for card in cards:
                title = _optional(card, ".post-title")
                if not title:
                    continue
                organization = re.sub(r"\s+", " ", title).strip()
                domain_match = re.search(
                    r"(?<![@\w])(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\b",
                    organization, re.I,
                )
                domain = domain_match.group(0).casefold().removeprefix("www.") if domain_match else None
                description = _optional(card, ".post-block-text")
                date_text = _optional(card, ".updated-post-date")
                listed_date = None
                if date_text:
                    match = re.search(r"\b\d{1,2}\s+[A-Za-z]{3},\s+20\d{2},\s+\d{2}:\d{2}\s+UTC\b", date_text)
                    if match:
                        try:
                            listed_date = datetime.strptime(match.group(0), "%d %b, %Y, %H:%M UTC").replace(tzinfo=timezone.utc).isoformat()
                        except ValueError:
                            pass

                timer_text = _optional(card, ".post-timer .timer")
                deadline = None
                remaining = None
                timer_match = re.fullmatch(r"\s*(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s\s*)?", timer_text or "")
                if timer_match and timer_text:
                    days, hours, minutes, seconds = (int(value or 0) for value in timer_match.groups())
                    remaining = days * 86400 + hours * 3600 + minutes * 60 + seconds
                    deadline = (captured_at + timedelta(seconds=remaining)).isoformat()
                status = "published" if card.find_elements("css selector", ".post-timer-end") else "yet_to_publish" if timer_text else None
                post_url = card.get_attribute("href") or ""
                post_id = re.search(r"/post/([^/?#]+)", post_url)
                views = _optional(card, ".views span")
                descriptions = [description] if description else []
                if views:
                    descriptions.append(f"Views: {views}")
                records.append({
                    "source_record_id": post_id.group(1) if post_id else (domain or organization.casefold()),
                    "organization": organization,
                    "country": None,
                    "listed_date": listed_date,
                    "source_created_at": listed_date,
                    "website": f"https://{domain}" if domain else None,
                    "domain": domain,
                    "categories": [],
                    "descriptions": descriptions,
                    "source_publication_status": status,
                    "estimated_publish_at": deadline,
                    "countdown_captured_at": captured_at.isoformat() if timer_text else None,
                    "countdown_seconds_at_capture": remaining,
                    "countdown_raw": timer_text,
                })
            if not records and not errors:
                errors.append("no .post-block victim records found after entry and queue")

        pages = []
        if records:
            screenshot, dimensions = _screenshot(driver)
            pages.append({
                "url": driver.current_url,
                "title": driver.title,
                "status_code": 200,
                "content_type": "text/html",
                "records": records,
                "response_metadata": {"date_inspection": inspect_markup_dates(driver.page_source, records)},
                "screenshot": screenshot,
                "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                "screenshot_dimensions": dimensions,
            })
        return {"site": site, "pages": pages, "pages_visited": 1, "errors": errors, "challenge": challenge}
    finally:
        driver.quit()


def _termite_values(payload) -> list[dict]:
    """Normalize Termite's public blog API list/envelope response."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "posts", "blogs", "companies", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _termite_values(value)
            if nested:
                return nested
    return []


def _termite_field(item: dict, *keys: str):
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def _collect_termite_api(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    """Collect the public records from the API used by Termite's React UI."""
    if not site.api_url:
        return {"site": site, "pages": [], "pages_visited": 0,
                "errors": ["Termite public API URL is not configured"], "challenge": None}
    proxy = f"socks5h://{tor_host}:{tor_port}"
    try:
        response = requests.get(
            site.api_url,
            proxies={"http": proxy, "https": proxy},
            timeout=(15, 45),
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"Termite public API request failed: {type(exc).__name__}: {str(exc)[:300]}"],
                "challenge": None}

    records = []
    for item in _termite_values(payload):
        organization = _termite_field(item, "companyName", "company_name", "organization", "name", "title")
        if not organization:
            continue
        organization = re.sub(r"\s+", " ", BeautifulSoup(html.unescape(str(organization)), "html.parser").get_text(" ", strip=True))
        address = _termite_field(item, "domain", "website", "url", "address")
        domain = None
        if address:
            candidate = str(address).strip()
            host = urlparse(candidate if "://" in candidate else f"https://{candidate}").hostname
            if host and "." in host and not host.endswith(".onion"):
                domain = host.casefold().removeprefix("www.")
        country = _termite_field(item, "country", "countryCode", "country_code", "location")
        date = _termite_field(item, "leakDate", "leak_date", "publishDate", "publishedAt", "published_at", "createdAt", "created_at", "date")
        status = str(_termite_field(item, "publicationStatus", "publication_status", "status") or "").casefold()
        published_at = _termite_field(item, "publishedAt", "published_at")
        publication_status = "published" if status in {"published", "disclosed", "leaked"} or published_at else None
        description = _termite_field(item, "description", "summary", "content", "text")
        records.append({
            "source_record_id": str(_termite_field(item, "_id", "id", "slug", "uuid") or organization.casefold()),
            "organization": organization,
            "country": str(country) if country else None,
            "listed_date": str(date) if date else None,
            "website": f"https://{domain}" if domain else None,
            "domain": domain,
            "categories": [],
            "descriptions": [str(description)] if description else [],
            "source_publication_status": publication_status,
        })

    errors = [] if records else ["Termite public API returned no recognized victim records"]
    return {
        "site": site,
        "pages": [{
            "url": response.url,
            "title": "Termite public victim API",
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "application/json"),
            "records": records,
            "screenshot": b"",
        }] if records else [],
        "pages_visited": 1,
        "errors": errors,
        "challenge": None,
    }


def _text(element) -> str:
    return re.sub(r"\s+", " ", (element.text or "")).strip()


def _optional(element, selector: str) -> str | None:
    found = element.find_elements("css selector", selector)
    value = _text(found[0]) if found else ""
    return value or None


def _challenge(driver) -> str | None:
    body = ""
    try:
        nodes = driver.find_elements("tag name", "body")
        body = _text(nodes[0]).lower()[:12000] if nodes else ""
    except WebDriverException:
        pass
    check = f"{driver.current_url} {driver.title} {body}".lower()
    if any(value in check for value in (
        "captcha", "enter the characters shown", "verify you are human",
        "verification", "you have been blocked", "access denied",
        "checking your browser", "proof of work", "ddos-guard",
        "checking that you are human", "please enable javascript to visit the site",
    )):
        return "challenge or access restriction detected; page was not bypassed"
    return None


def _extract(driver, site: JavascriptLeakSite) -> list[dict]:
    if site.slug == "atomsilo":
        rows = []
        captured_at = datetime.now(timezone.utc)
        for card in driver.find_elements("css selector", ".leak-card"):
            name = _optional(card, ".leak-title")
            if not name:
                continue
            domain = _optional(card, ".leak-domain")
            domain = re.sub(r"^www\.", "", domain.strip().casefold()) if domain else None
            size = _optional(card, ".data-value")
            data_types = [
                _text(item).lstrip("- ")
                for item in card.find_elements("css selector", ".leak-data li")
                if _text(item)
            ]
            published = card.find_elements("css selector", ".published-img[alt*=published i],.published-img")
            countdowns = card.find_elements("css selector", ".countdown[data-date]")
            deadline = None
            raw_deadline = countdowns[0].get_attribute("data-date") if countdowns else None
            if raw_deadline:
                try:
                    deadline = datetime.fromisoformat(raw_deadline.strip().replace("Z", "+00:00"))
                    if deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=timezone.utc)
                    deadline = deadline.astimezone(timezone.utc)
                except ValueError:
                    deadline = None
            status = "published" if published else "yet_to_publish" if countdowns else None
            post_links = card.find_elements("css selector", "a[href*='post.html']")
            post_url = post_links[0].get_attribute("href") if post_links else ""
            post_id = re.search(r"[?&]id=([^&#]+)", post_url)
            description_parts = []
            if size:
                description_parts.append(f"Data size: {size}")
            if data_types:
                description_parts.append("Data contains: " + ", ".join(data_types))
            remaining = max(0, int((deadline - captured_at).total_seconds())) if deadline else None
            rows.append({
                "source_record_id": post_id.group(1) if post_id else (domain or name.casefold()),
                "organization": re.sub(r"\s+", " ", name).strip(),
                "country": None,
                "listed_date": None,
                "source_created_at": None,
                "domain": domain,
                "categories": [],
                "descriptions": [". ".join(description_parts)] if description_parts else [],
                "source_publication_status": status,
                "estimated_publish_at": deadline.isoformat() if deadline else None,
                "countdown_captured_at": captured_at.isoformat() if countdowns else None,
                "countdown_seconds_at_capture": remaining,
                "countdown_raw": raw_deadline,
            })
        return rows

    if site.slug == "play_ransomware":
        candidates = driver.execute_script("""
          return [...document.querySelectorAll('th.News')].map(card => {
            const direct = [...card.childNodes].filter(n => n.nodeType === Node.TEXT_NODE)
              .map(n => n.textContent.trim()).find(Boolean) || '';
            return {name: direct, text: card.innerText || ''};
          });
        """)
        rows = []
        for candidate in candidates:
            text = re.sub(r"\s+", " ", candidate.get("text", ""))
            name = re.sub(r"\s+", " ", candidate.get("name", "")).strip(" |\t\r\n")
            country_match = re.search(r"\b(United States|United Kingdom|Germany|France|Italy|Spain|Canada|Australia|Netherlands|Brazil|Japan|Ireland|Norway)\b", text, re.I)
            if country_match:
                name = text[:country_match.start()].strip(" |\t\r\n")
            if not name or name.casefold() in {row["organization"].casefold() for row in rows}:
                continue
            country = country_match.group(1) if country_match else None
            domain_match = re.search(r"(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", text, re.I)
            date_match = re.search(r"publication date:\s*(20\d{2}-\d{2}-\d{2})", text, re.I)
            domain = domain_match.group(0).casefold().removeprefix("www.") if domain_match else None
            rows.append({"source_record_id": name.casefold(), "organization": name, "country": country,
                "listed_date": date_match.group(1) if date_match else None,
                "website": f"https://{domain}" if domain else None, "domain": domain,
                "categories": [], "descriptions": []})
        return rows

    candidates = driver.execute_script("""
        const [itemSelector, nameSelector, countrySelector, dateSelector] = arguments;
        const tidy = value => (value || '').replace(/\\s+/g, ' ').trim();
        let elements = [];
        try { if (itemSelector) elements = [...document.querySelectorAll(itemSelector)]; } catch (_) {}
        if (!elements.length) {
          elements = [...document.querySelectorAll('main h2,main h3,main h4,article h2,article h3,article h4')];
        }
        return elements.slice(0, 2500).map(item => {
          let titleNode = /^(H1|H2|H3|H4|TD)$/.test(item.tagName) ? item : null;
          if (!titleNode) { try { titleNode = item.querySelector(nameSelector); } catch (_) {} }
          const name = tidy(titleNode?.innerText);
          let scope = null;
          for (let node = titleNode, depth = 0; node && node !== document.body && depth < 7; node = node.parentElement, depth++) {
            const text = (node.innerText || '').trim();
            if (text.length < 1800 && /\\b(?:Country|Data)\\s*:/i.test(text)) { scope = node; break; }
          }
          scope = scope || titleNode?.closest('article,tr,li,[class*="card"],[class*="item"],[class*="victim"],[class*="company"],[class*="post"]') || item;
          let country = '', date = '';
          try { country = (scope.querySelector(countrySelector)?.innerText || '').trim(); } catch (_) {}
          try {
            const dateNode = scope.querySelector(dateSelector);
            date = tidy(dateNode?.getAttribute('datetime') || dateNode?.getAttribute('data-date') || dateNode?.innerText);
          } catch (_) {}
          return {name, country, date, text: (scope.innerText || '').trim()};
        }).filter(row => row.name);
    """, site.item_selector, site.name_selector, site.country_selector, site.date_selector)

    rows = []
    for candidate in candidates:
        name = re.sub(r"\s+", " ", candidate.get("name", "")).strip(" \t\r\n|:->")
        if site.slug == "dark_project":
            name = re.split(r"\s+Views:\s*\d+\b", name, maxsplit=1, flags=re.I)[0].strip()
        if len(name) < 2 or len(name) > 240 or name.casefold() in {
            "home", "about", "news", "leaks", "victims", "companies", "loading",
            "published", "more", "read more", "data leak", "contact", "search",
        }:
            continue
        if re.match(r"^(welcome\b|latest\s+(?:news|posts)|home\b|about\b|faq\b)", name, re.I):
            continue
        if site.slug == "global" and (name.casefold() == "who is next??" or re.match(r"^publication\s*\(", name, re.I)):
            continue
        if site.slug == "sovcali" and (name.casefold() == "latest entries" or name.casefold().startswith("[sell] lucid motors data auction")):
            continue
        normalized = name.casefold()
        if any(row["organization"].casefold() == normalized for row in rows):
            continue
        country = candidate.get("country") or None
        text = candidate.get("text", "")
        labelled_country = re.search(r"\bCountry\s*:\s*([^\r\n]+)", text, re.I)
        if labelled_country:
            country = labelled_country.group(1).strip()
        elif country:
            country = re.sub(r"\s+", " ", country).strip()
        if country:
            country = re.sub(r"^[\U0001F1E6-\U0001F1FF]{2}\s*", "", country).strip()
        if country:
            # Kairos card metadata places country, data size, views, and status
            # in one rendered block. Keep the country value only.
            country = re.split(
                r"\s+(?:Data|Views|Published|Download)\b.*$",
                re.sub(r"\s+", " ", country),
                maxsplit=1,
                flags=re.I,
            )[0].strip(" \t\r\n|:-")
            if len(country) > 48:
                country = None
        date = candidate.get("date") or None
        if not date:
            match = re.search(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", text)
            if match:
                date = match.group(0)
            else:
                match = re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2}\b", text, re.I)
                if match:
                    date = match.group(0)
                else:
                    match = re.search(r"\b\d{1,2}/\d{1,2}/20\d{2}\b", text)
                    if match:
                        try:
                            date = datetime.strptime(match.group(0), "%m/%d/%Y").date().isoformat()
                        except ValueError:
                            pass
        if not country:
            match = re.search(r"\bCountry\s*:\s*([^\r\n|]+)", text, re.I)
            if match:
                country = match.group(1).strip()
        domain = None
        domain_match = re.search(r"(?<![@\w])(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\b", text, re.I)
        if domain_match:
            domain = domain_match.group(0).casefold().removeprefix("www.")
        rows.append({
            "source_record_id": normalized,
            "organization": name,
            "country": country,
            "listed_date": date,
            "website": f"https://{domain}" if domain else None,
            "domain": domain,
            "categories": [],
            "descriptions": [],
        })
    return rows


def _collect_play_pages(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    """Play uses onclick-driven pagination; collect only listing cards."""
    driver = _make_driver(tor_host, tor_port)
    driver.set_page_load_timeout(_page_timeout_for_site(site))
    pages, errors, visited = [], [], set()
    challenge = None
    try:
        try:
            driver.get(site.url)
        except TimeoutException:
            errors.append(f"page load exceeded {JS_PAGE_TIMEOUT_SECONDS}s: {site.url}")
        WebDriverWait(driver, JS_RENDER_WAIT_SECONDS).until(
            lambda browser: browser.execute_script("return document.readyState") in ("interactive", "complete")
        )
        current = 1
        while len(visited) < PLAY_MAX_PAGES:
            challenge = _challenge(driver)
            if challenge:
                errors.append(challenge)
                break
            records = _extract(driver, site)
            date_inspection = inspect_markup_dates(driver.page_source, records)
            if records:
                screenshot, dimensions = _screenshot(driver)
                pages.append({"url": driver.current_url, "title": driver.title, "status_code": 200,
                    "content_type": "text/html", "records": records, "screenshot": screenshot,
                    "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                    "screenshot_dimensions": dimensions,
                    "response_metadata": {"pagination_page": current, "date_inspection": date_inspection}})
            visited.add(current)
            # Play displays a moving window of page numbers; refresh controls
            # after each AJAX navigation so intermediate pages are not skipped.
            controls = driver.find_elements("css selector", ".Page[onclick]")
            page_numbers = sorted({int(match.group(1)) for control in controls
                if (match := re.search(r"goto_page\(['\"]?(\d+)", control.get_attribute("onclick") or ""))})
            following = next((number for number in page_numbers if number > current), None)
            if following is None:
                break
            old_first = driver.execute_script("return document.querySelector('th.News')?.childNodes[0]?.textContent || ''")
            driver.execute_script("goto_page(arguments[0])", str(following))
            try:
                WebDriverWait(driver, 20).until(lambda browser: browser.execute_script(
                    "return (document.querySelector('th.News')?.childNodes[0]?.textContent || '') !== arguments[0]",
                    old_first))
            except TimeoutException:
                errors.append(f"Play pagination to page {following} did not change the first listing card")
                break
            current = following
        if not pages and not errors:
            errors.append("no victim records matched Play listing cards")
    except (TimeoutException, WebDriverException) as exc:
        errors.append(f"{type(exc).__name__}: {str(exc)[:350]}")
    finally:
        driver.quit()
    if not pages and site.alternate_urls:
        fallback = replace(site, url=site.alternate_urls[0], alternate_urls=())
        alternate_result = _collect_play_pages(fallback, tor_host, tor_port)
        alternate_result["site"] = site
        if not alternate_result.get("pages"):
            alternate_result["errors"] = errors + alternate_result.get("errors", [])
        return alternate_result
    return {"site": site, "pages": pages, "pages_visited": len(visited), "errors": errors, "challenge": challenge}


def collect_javascript_site_pages(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    if site.slug == "blackx":
        return collect_blackx(site, tor_host, tor_port)
    if site.slug == "insomnia":
        return collect_insomnia(site, tor_host, tor_port)
    if site.slug == "storm":
        return collect_storm(site, tor_host, tor_port)
    if site.slug == "settra":
        return collect_settra(site, tor_host, tor_port)
    if site.slug == "lockbit":
        return _collect_lockbit_listing(site, tor_host, tor_port)
    if site.slug == "everest":
        return _collect_everest_listing(site, tor_host, tor_port)
    if site.slug == "exitium":
        return _collect_exitium_listing(site, tor_host, tor_port)
    if site.slug == "abyss":
        return _collect_abyss_listing(site, tor_host, tor_port)
    if site.slug == "play_ransomware":
        return _collect_play_pages(site, tor_host, tor_port)
    if site.slug == "titan":
        return _collect_titan_listing(site, tor_host, tor_port)
    if site.slug == "termite_ransomware":
        return _collect_termite_api(site, tor_host, tor_port)
    driver = _make_driver(tor_host, tor_port)
    page_timeout = _page_timeout_for_site(site)
    driver.set_page_load_timeout(page_timeout)
    origin = f"{urlparse(site.url).scheme}://{urlparse(site.url).netloc}"
    queue, visited, pages, errors = [site.url], set(), [], []
    challenge = None
    try:
        while queue and len(visited) < MAX_PAGES_PER_SITE:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                try:
                    driver.get(url)
                except TimeoutException:
                    errors.append(f"page load exceeded {page_timeout}s: {url}")
                WebDriverWait(driver, JS_RENDER_WAIT_SECONDS).until(
                    lambda browser: browser.execute_script("return document.readyState") in ("interactive", "complete")
                )
                time.sleep(3)
                # A navigation timeout can leave Selenium on the previous page.
                # Never associate a stale page's records with this site.
                if urlparse(driver.current_url).netloc.lower() != urlparse(origin).netloc.lower():
                    errors.append(f"navigation did not reach the requested site: {url}")
                    continue
                challenge = _challenge(driver)
                if challenge:
                    errors.append(challenge)
                    break
                records = _extract(driver, site)
                date_inspection = inspect_markup_dates(driver.page_source, records)
                if not records:
                    errors.append("no victim records matched the rendered listing selectors")
                    continue
                screenshot, dimensions = _screenshot(driver)
                pages.append({
                    "url": driver.current_url,
                    "title": driver.title,
                    "status_code": 200,
                    "content_type": "text/html",
                    "records": records,
                    "response_metadata": {"date_inspection": date_inspection},
                    "screenshot": screenshot,
                    "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                    "screenshot_dimensions": dimensions,
                })
                for next_url in _pagination_links(driver, origin):
                    if next_url not in visited and next_url not in queue and len(visited) + len(queue) < MAX_PAGES_PER_SITE:
                        queue.append(next_url)
                if site.slug == "play_ransomware" and len(visited) < MAX_PAGES_PER_SITE:
                    next_page = len(visited)
                    controls = driver.find_elements("css selector", ".Page[onclick]")
                    available = {re.search(r"goto_page\(['\"]?(\d+)", c.get_attribute("onclick") or "").group(1)
                                 for c in controls if re.search(r"goto_page\(['\"]?(\d+)", c.get_attribute("onclick") or "")}
                    if str(next_page) in available:
                        old_first = records[0]["organization"] if records else ""
                        driver.execute_script("goto_page(arguments[0])", str(next_page))
                        try:
                            WebDriverWait(driver, 15).until(lambda browser: browser.execute_script(
                                "return (document.querySelector('th.News')?.childNodes[0]?.textContent || '').trim() !== arguments[0]",
                                old_first))
                        except TimeoutException:
                            pass
                        queue.append(f"{origin}/index.php?page={next_page}")
            except WebDriverException as exc:
                errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:350]}")
                break
    finally:
        driver.quit()
    return {"site": site, "pages": pages, "pages_visited": len(visited), "errors": errors, "challenge": challenge}

