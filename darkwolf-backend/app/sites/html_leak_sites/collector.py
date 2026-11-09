import base64
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urldefrag, urlencode, urljoin, urlparse, urlsplit

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from app.sites.html_leak_sites.registry import HtmlLeakSite
from app.sites.markup_date_inspector import inspect_markup_dates


PAGE_TIMEOUT_SECONDS = 75
SLOW_HTML_SITE_PAGE_TIMEOUT_SECONDS = 150
VERY_SLOW_HTML_SITE_PAGE_TIMEOUT_SECONDS = 300
VERY_SLOW_HTML_SITE_SLUGS = {"anubis"}
SLOW_HTML_SITE_SLUGS = {
    "imnotavillain", "blackwater", "cmd_organization", "falcon", "karma_leaks", "kazu", "pear_ransomware",
}
RENDER_WAIT_SECONDS = 35
MAX_PAGES_PER_SITE = 12
CHALLENGE_MARKERS = (
    "captcha", "verify session", "verify your path", "verify you are human",
    "proof of work", "anubis", "turnstile", "ddos-guard",
    "checking your browser", "match the pattern", "slide to verify",
    "i'm not a robot",
)


def _text(element) -> str:
    return re.sub(r"\s+", " ", (element.text or "")).strip()


def _optional(element, selector: str) -> str | None:
    found = element.find_elements("css selector", selector)
    value = _text(found[0]) if found else ""
    return value or None


def _strip_country_flag(value: str | None) -> tuple[str | None, str | None]:
    """Extract a leading regional-indicator flag and return its ISO alpha-2."""
    if not value:
        return value, None
    match = re.match(r"^\s*([\U0001F1E6-\U0001F1FF]{2})\s*", value)
    if not match:
        return value, None
    flag = match.group(1)
    country = "".join(chr(ord("A") + ord(character) - 0x1F1E6) for character in flag)
    organization = value[match.end():].strip(" \t\r\n|:-")
    return organization or value, country


def _parse_kazu_countdown(entry: dict) -> dict:
    captured_at = datetime.fromisoformat(
        (entry.get("captured_at") or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
    )
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    captured_at = captured_at.astimezone(timezone.utc)

    candidates = entry.get("countdown_candidates") or []
    values = []
    for candidate in candidates:
        if candidate.get("text"):
            values.append(candidate["text"].strip())
        values.extend(str(value).strip() for value in (candidate.get("attributes") or {}).values() if value)

    deadline = None
    seconds = None
    absolute_keys = re.compile(r"(target|deadline|expires?|publish|datetime|timestamp|date)$", re.I)
    for candidate in candidates:
        for key, raw in (candidate.get("attributes") or {}).items():
            value = str(raw).strip()
            if not value:
                continue
            normalized_key = re.sub(r"^data-", "", key, flags=re.I)
            if absolute_keys.search(normalized_key):
                if re.fullmatch(r"\d{10,13}", value):
                    epoch = int(value)
                    deadline = datetime.fromtimestamp(epoch / (1000 if epoch > 10**11 else 1), timezone.utc)
                else:
                    parsed = _parse_datetime(value)
                    if parsed:
                        deadline = parsed
                if deadline:
                    break
        if deadline:
            break

    if deadline is None:
        for value in values:
            if re.fullmatch(r"\d{10,13}", value):
                epoch = int(value)
                candidate_deadline = datetime.fromtimestamp(epoch / (1000 if epoch > 10**11 else 1), timezone.utc)
                if candidate_deadline > captured_at - timedelta(days=1):
                    deadline = candidate_deadline
                    break
            parsed = _parse_datetime(value)
            if parsed and parsed > captured_at - timedelta(days=1):
                deadline = parsed
                break

    if deadline is None:
        duration_patterns = (
            (re.compile(r"(?:(\d+)\s*d(?:ays?)?\s*)?(?:(\d+)\s*h(?:ours?)?\s*)?(?:(\d+)\s*m(?:in(?:utes?)?)?\s*)?(?:(\d+)\s*s(?:ec(?:onds?)?)?)?", re.I), "units"),
            (re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?::(\d{2}))?$"), "clock"),
        )
        duration_values = []
        for value in values:
            duration_values.extend(
                part.strip()
                for part in re.split(r"[—–|]", value)
                if part.strip()
            )
            duration_values.append(value)
        for value in duration_values:
            for pattern, kind in duration_patterns:
                match = pattern.fullmatch(value.strip())
                if not match or not any(match.groups()):
                    continue
                parts = [int(part or 0) for part in match.groups()]
                if kind == "units":
                    days, hours, minutes, secs = parts
                elif len(value.strip().split(":")) == 4:
                    days, hours, minutes, secs = parts
                else:
                    days, hours, minutes, secs = 0, parts[1], parts[2], parts[3]
                seconds = days * 86400 + hours * 3600 + minutes * 60 + secs
                deadline = captured_at + timedelta(seconds=seconds)
                break
            if deadline:
                break

    source_status = (entry.get("source_publication_status") or "").casefold()
    if source_status not in {"published", "yet_to_publish"}:
        source_status = "yet_to_publish" if deadline else None
    if deadline and seconds is None:
        seconds = max(0, int((deadline - captured_at).total_seconds()))
    return {
        "estimated_publish_at": deadline.isoformat() if deadline else None,
        "countdown_captured_at": captured_at.isoformat() if candidates else None,
        "countdown_seconds_at_capture": seconds,
        "countdown_raw": " | ".join(dict.fromkeys(values))[:500] or None,
        "source_publication_status": source_status,
    }


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _challenge(driver, site_slug: str | None = None) -> str | None:
    body_nodes = driver.find_elements("tag name", "body")
    body = _text(body_nodes[0]).lower()[:12000] if body_nodes else ""
    check = f"{driver.current_url} {driver.title} {body}".lower()
    markers = CHALLENGE_MARKERS
    # The ransomware group itself is named Anubis; that word alone is not a
    # proof-of-work challenge signal on its own leak site.
    if site_slug == "anubis":
        markers = tuple(item for item in markers if item != "anubis")
    marker = next((item for item in markers if item in check), None)
    return f"challenge detected: {marker}" if marker else None


def _record(rows: list[dict], site: HtmlLeakSite, name: str | None,
            country: str | None = None, listed_date: str | None = None,
            source_record_id: str | None = None, domain: str | None = None,
            clear_leak_date: bool = False) -> None:
    if not name:
        return
    name = re.sub(r"\s+", " ", name).strip(" \t\r\n|:-")
    if len(name) < 2 or name.lower() in {
        "paid", "new", "victims", "entities", "leaked data",
        "important announcement", "a little gift of exclusive data for everyone",
    }:
        return
    normalized = name.casefold()
    if any(row["organization"].casefold() == normalized for row in rows):
        return
    rows.append({
        "organization": name,
        "country": country,
        "listed_date": listed_date,
        "source_created_at": None,
        "source_record_id": source_record_id,
        "domain": domain,
        "clear_leak_date": clear_leak_date,
    })


def _extract_non(driver, site: HtmlLeakSite) -> list[dict]:
    """Read all N0n tab cards from the DOM, including inactive hidden tabs."""
    captured_at = datetime.now(timezone.utc)
    cards = driver.execute_script("""
      return [...document.querySelectorAll('.pane .card')].map(card => ({
        name: card.querySelector('.vname')?.textContent?.trim() || '',
        meta: card.querySelector('.meta')?.textContent?.trim() || '',
        badge: card.querySelector('.badge')?.textContent?.trim() || '',
        count: card.querySelector('.count')?.innerText?.trim() || card.querySelector('.count')?.textContent?.trim() || '',
        countClass: card.querySelector('.count')?.className || '',
        timerStyle: card.querySelector('.count .ws')?.getAttribute('style') || '',
        note: card.querySelector('.note')?.textContent?.trim() || '',
        classes: card.className || '',
        id: card.id || '',
        modalHref: card.querySelector('a[href^="#v-"]')?.getAttribute('href') || ''
      }));
    """)
    modals = driver.execute_script("""
      return [...document.querySelectorAll('.modal[id^="v-"]')].map(modal => ({
        id: modal.id.slice(2),
        name: modal.querySelector('h3')?.textContent?.trim() || ''
      }));
    """)
    domain_by_name = {
        row["name"].casefold(): row["id"].casefold()
        for row in modals
        if row.get("name") and re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,63}", row.get("id", ""), re.I)
    }
    country_aliases = {
        "usa": "United States", "us": "United States", "united states": "United States",
        "uk": "United Kingdom", "united kingdom": "United Kingdom",
    }
    rows = []
    for card in cards:
        name = re.sub(r"\s+", " ", card.get("name", "")).strip()
        if not name:
            continue
        classes = set(card.get("classes", "").split())
        count_classes = set(card.get("countClass", "").split())
        meta = re.sub(r"\s+", " ", card.get("meta", "")).strip()
        country = None
        if "·" in meta:
            location = meta.rsplit("·", 1)[-1].strip()
            tail = location.rsplit(",", 1)[-1].strip()
            country = country_aliases.get(location.casefold(), country_aliases.get(tail.casefold()))

        note = card.get("note", "")
        deadline_match = re.search(r"\bdeadline\s+(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+UTC\b", note, re.I)
        deadline = None
        if deadline_match:
            deadline = _parse_datetime(deadline_match.group(1).replace(" ", "T") + ":00+00:00")
        seconds = max(0, int((deadline - captured_at).total_seconds())) if deadline else None
        if deadline is None:
            duration_match = re.search(r"--d:\s*(-?\d+)s", card.get("timerStyle", ""))
            delay_match = re.search(r"--dl:\s*(-?\d+)s", card.get("timerStyle", ""))
            if duration_match:
                seconds = int(duration_match.group(1)) + int(delay_match.group(1) if delay_match else 0)
                seconds = max(0, seconds)
                deadline = captured_at + timedelta(seconds=seconds)

        if "honor" in classes:
            status = "honored"
        elif "leaked" in classes or "expired" in count_classes or (deadline and deadline <= captured_at):
            status = "published"
        elif "public" in classes or "pend" in classes or deadline:
            status = "yet_to_publish"
        else:
            status = None
        listed_date = deadline.isoformat() if status == "published" and deadline else None
        estimate = deadline.isoformat() if status == "yet_to_publish" and deadline else None
        source_id = card.get("modalHref", "").removeprefix("#v-") or card.get("id") or name.casefold()
        _record(rows, site, name, country, listed_date, source_record_id=source_id,
                domain=domain_by_name.get(name.casefold()))
        if rows and rows[-1]["organization"].casefold() == name.casefold():
            rows[-1].update({
                "source_publication_status": status,
                "estimated_publish_at": estimate,
                "countdown_captured_at": captured_at.isoformat() if status == "yet_to_publish" and card.get("count") else None,
                "countdown_seconds_at_capture": seconds if status == "yet_to_publish" else None,
                "countdown_raw": card.get("count") if status == "yet_to_publish" else None,
                "descriptions": [],
            })
    return rows


def _extract(driver, site: HtmlLeakSite) -> list[dict]:
    rows: list[dict] = []
    group = site.slug

    if group == "beast_leaks":
        captured_at = datetime.now(timezone.utc)
        for card in driver.find_elements("css selector", ".catalog > a.card"):
            title = _optional(card, ".card-head h3")
            if not title:
                continue
            info = {}
            for item in card.find_elements("css selector", ".card-info > div"):
                label = _text(item)
                match = re.match(r"\s*([^:]+):\s*(.*?)\s*$", label)
                if match:
                    info[match.group(1).casefold()] = match.group(2)

            raw_date = _optional(card, ".card-info .date")
            listed_date = None
            if raw_date:
                try:
                    date_format = "%Y.%m.%d" if re.match(r"^20\d{2}[./-]", raw_date) else "%d.%m.%Y"
                    listed_date = datetime.strptime(raw_date.replace("/", ".").replace("-", "."), date_format).date().isoformat()
                except ValueError:
                    listed_date = None

            timer_node = card.find_elements("css selector", ".card-counter .timer")
            timer_raw = _text(timer_node[0]) if timer_node else ""
            normalized_timer = re.sub(r"\s+", "", timer_raw).casefold()
            counter_nodes = card.find_elements("css selector", ".card-counter[data-date]")
            deadline = None
            if counter_nodes:
                deadline = _parse_datetime(counter_nodes[0].get_attribute("data-date"))
            unpublished = bool(card.find_elements("css selector", ".card-info .unpublished"))
            if "published" in normalized_timer or "leaked" in normalized_timer:
                publication_status = "published"
            elif deadline and deadline > captured_at:
                publication_status = "yet_to_publish"
            elif deadline or not unpublished:
                publication_status = "published" if deadline else None
            else:
                publication_status = "yet_to_publish"

            seconds = max(0, int((deadline - captured_at).total_seconds())) if deadline and publication_status == "yet_to_publish" else None
            website = info.get("website", "").strip()
            domain = website.casefold().removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/")
            if not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain):
                domain = None
            source_id = urlparse(card.get_attribute("href") or "").path.rstrip("/").rsplit("/", 1)[-1] or title.casefold()
            _record(rows, site, title, listed_date=listed_date, source_record_id=source_id, domain=domain)
            if rows and rows[-1]["organization"].casefold() == title.casefold():
                descriptions = [
                    _text(node) for node in card.find_elements("css selector", ".card-text p")
                    if _text(node)
                ]
                for label in ("revenue", "data size"):
                    value = info.get(label)
                    if value and value != "-":
                        descriptions.append(f"{label.title()}: {value}")
                rows[-1].update({
                    "source_publication_status": publication_status,
                    "estimated_publish_at": deadline.isoformat() if publication_status == "yet_to_publish" and deadline else None,
                    "countdown_captured_at": captured_at.isoformat() if deadline and publication_status == "yet_to_publish" else None,
                    "countdown_seconds_at_capture": seconds,
                    "countdown_raw": timer_raw or None,
                    "descriptions": descriptions,
                })
        return rows

    if group == "arachna":
        # Arachna is a static HTML listing. Each victim is a `.post` card;
        # the site currently exposes the organization in its h2 and may show
        # a downloadable-file link, but no reliable leak-date field.
        for card in driver.find_elements("css selector", ".container .post"):
            title = _optional(card, "h2")
            if not title:
                continue
            note_match = re.search(r"\s*\((Leaking some patient data)\)\s*$", title, re.I)
            if note_match:
                title = title[:note_match.start()].strip()
            link = card.find_elements("css selector", "a[href]")
            date_node = card.find_elements("css selector", "time[datetime], time, [data-date]")
            date_value = None
            if date_node:
                date_value = (
                    date_node[0].get_attribute("datetime")
                    or date_node[0].get_attribute("data-date")
                    or _text(date_node[0])
                )
            date_match = re.search(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", date_value or "")
            _record(rows, site, title,
                    listed_date=date_match.group(0) if date_match else None,
                    source_record_id=title.casefold())
            if rows and rows[-1]["organization"].casefold() == title.casefold():
                rows[-1]["source_publication_status"] = "published" if link else None
                descriptions = [
                    text for paragraph in card.find_elements("css selector", "p")
                    if (text := _text(paragraph)) and text.casefold() != "files: download"
                ]
                if note_match:
                    descriptions.append(note_match.group(1))
                rows[-1]["descriptions"] = descriptions
        return rows

    if group == "non":
        return _extract_non(driver, site)

    if group in {"non", "payload"}:
        captured_at = datetime.now(timezone.utc)
        cards = driver.find_elements(
            "css selector",
            ".pane .card" if group == "non" else "a.card-link article.card",
        )
        non_domains = {}
        if group == "non":
            for modal in driver.find_elements("css selector", ".modal[id^='v-']"):
                headings = modal.find_elements("css selector", "h3")
                if not headings:
                    continue
                modal_id = (modal.get_attribute("id") or "").removeprefix("v-")
                if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,63}", modal_id, re.I):
                    non_domains[_text(headings[0]).casefold()] = modal_id.casefold()
        country_aliases = {
            "usa": "United States", "us": "United States", "united states": "United States",
            "uk": "United Kingdom", "united kingdom": "United Kingdom",
            "south korea": "South Korea", "new south wales, australia": "Australia",
        }
        for card in cards:
            raw_name = _optional(card, ".vname" if group == "non" else ".title")
            if not raw_name:
                continue
            name = raw_name
            meta = _optional(card, ".meta") if group == "non" else None
            country = None
            if meta and "·" in meta:
                location = meta.rsplit("·", 1)[-1].strip()
                country = country_aliases.get(location.casefold())
                if not country:
                    tail = location.rsplit(",", 1)[-1].strip()
                    country = country_aliases.get(tail.casefold(), tail if len(tail) <= 48 else None)

            card_classes = set(card.get_attribute("class").split())
            timer_text = _optional(card, ".count" if group == "non" else ".timer")
            note = _optional(card, ".note") if group == "non" else None
            deadline = None
            deadline_match = re.search(r"\bdeadline\s+(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+UTC\b", note or "", re.I)
            if deadline_match:
                deadline = _parse_datetime(deadline_match.group(1).replace(" ", "T") + ":00+00:00")

            seconds = None
            if deadline:
                seconds = max(0, int((deadline - captured_at).total_seconds()))
            elif group == "payload" and timer_text:
                timer_match = re.fullmatch(r"\s*(\d+)d\s+(\d+)h\s+(\d+)m(?:\s+(\d+)s)?\s*", timer_text)
                if timer_match:
                    days, hours, minutes, secs = (int(value or 0) for value in timer_match.groups())
                    seconds = days * 86400 + hours * 3600 + minutes * 60 + secs
                    if seconds > 0:
                        deadline = captured_at + timedelta(seconds=seconds)

            if group == "non":
                if "honor" in card_classes:
                    status = "honored"
                elif "leaked" in card_classes or ("expired" in set((card.find_elements("css selector", ".count")[0].get_attribute("class") or "").split()) if card.find_elements("css selector", ".count") else False):
                    status = "published"
                else:
                    status = "yet_to_publish" if deadline or timer_text else None
                listed_date = deadline.isoformat() if status == "published" and deadline else None
                estimate = deadline.isoformat() if status == "yet_to_publish" and deadline else None
                source_id = card.get_attribute("id")
                modal_link = card.find_elements("css selector", "a[href^='#v-']")
                if modal_link:
                    source_id = modal_link[0].get_attribute("href").rsplit("#v-", 1)[-1]
                if not source_id:
                    source_id = name.casefold()
                _record(rows, site, name, country, listed_date, source_record_id=source_id,
                        domain=non_domains.get(name.casefold()))
                if rows and rows[-1]["organization"].casefold() == name.casefold():
                    rows[-1].update({
                        "source_publication_status": status,
                        "estimated_publish_at": estimate,
                        "countdown_captured_at": captured_at.isoformat() if timer_text and status == "yet_to_publish" else None,
                        "countdown_seconds_at_capture": seconds if status == "yet_to_publish" else None,
                        "countdown_raw": timer_text if status == "yet_to_publish" else None,
                        "descriptions": [],
                    })
            else:
                timer_node = card.find_elements("css selector", ".timer")
                expired = bool(timer_node and "timer-expired" in (timer_node[0].get_attribute("class") or "").split())
                status = "published" if expired or not seconds else "yet_to_publish"
                source_link = card.find_elements("xpath", "./ancestor::a[1]")
                source_id = source_link[0].get_attribute("href") if source_link else name.casefold()
                source_id = urlparse(source_id).path.rsplit("/", 1)[-1] if "/" in source_id else source_id
                body = _optional(card, ".body") or ""
                title_domain_match = re.search(r"(?:\||·)\s*((?:[a-z0-9-]+\.)+[a-z]{2,})\b", raw_name, re.I)
                domain_match = title_domain_match or re.search(r"\(([a-z0-9.-]+\.[a-z]{2,})\)", body, re.I)
                domain = domain_match.group(1).casefold().removeprefix("www.") if domain_match else None
                if title_domain_match:
                    name = raw_name[:title_domain_match.start()].strip(" |·-")
                size = _optional(card, ".company-size")
                descriptions = [f"Data size: {size}"] if size else []
                _record(rows, site, name, listed_date=None, source_record_id=source_id, domain=domain)
                if rows and rows[-1]["organization"].casefold() == name.casefold():
                    rows[-1].update({
                        "source_publication_status": status,
                        "estimated_publish_at": deadline.isoformat() if status == "yet_to_publish" and deadline else None,
                        "countdown_captured_at": captured_at.isoformat() if timer_text and status == "yet_to_publish" else None,
                        "countdown_seconds_at_capture": seconds if status == "yet_to_publish" else None,
                        "countdown_raw": timer_text,
                        "descriptions": descriptions,
                    })
    elif group == "genesis":
        for card in driver.find_elements("css selector", "section.block-bg"):
            title = _optional(card, "h2")
            if not title:
                continue
            date_match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", _text(card))
            links = card.find_elements("css selector", "a[href]")
            source_id = urlparse(links[0].get_attribute("href")).path.strip("/") if links else title.casefold()
            _record(rows, site, title, listed_date=date_match.group(0) if date_match else None,
                    source_record_id=source_id)
    elif group == "anubis":
        for card in driver.find_elements("css selector", ".bg-secondary-2"):
            titles = card.find_elements("css selector", "h5.fw-bold")
            _record(rows, site, _text(titles[0]) if titles else None)
    elif group == "brain_cipher":
        for card in driver.find_elements("css selector", ".news-item"):
            title = _optional(card, ".headline")
            body = _text(card)
            _record(rows, site, title, listed_date=_optional(card, "time"),
                    source_record_id=title)
            if rows and rows[-1]["organization"] == title:
                rows[-1]["source_publication_status"] = (
                    "yet_to_publish" if re.search(r"\bPENDING\b", body, re.I)
                    else "published" if re.search(r"\bRELEASED\b", body, re.I)
                    else None
                )
    elif group == "deadlock_ransomware":
        for card in driver.find_elements("css selector", ".post"):
            title = _optional(card, ".post-title")
            body = _text(card)
            _record(rows, site, title, source_record_id=title)
            if rows and rows[-1]["organization"] == title:
                rows[-1]["source_publication_status"] = (
                    "published" if re.search(r"\bPublished\b", body, re.I)
                    else "yet_to_publish" if re.search(r"Publishes after:", body, re.I)
                    else None
                )
    elif group == "dire_wolf":
        for card in driver.find_elements("css selector", ".card"):
            title = _optional(card, ".card-title")
            organization, country = _strip_country_flag(title)
            body = _text(card)
            date_match = re.search(r"\bPublished:\s*(20\d{2}-\d{2}-\d{2})", body, re.I)
            link = card.find_elements("css selector", "a[href]")
            _record(rows, site, organization, country,
                    date_match.group(1) if date_match else None,
                    source_record_id=link[0].get_attribute("href") if link else organization)
    elif group == "imnotavillain":
        for card in driver.find_elements("css selector", ".leak-card,article,.card"):
            title = _optional(card, "h2,h3,h4,.title")
            if title and title.casefold() not in {"imnotavillain", "buy exclusion of your data"}:
                _record(rows, site, title, source_record_id=title)
    elif group == "interlock":
        for card in driver.find_elements("css selector", ".advert_item"):
            title = _optional(card, ".advert_info_title")
            info = _optional(card, ".advert_info_p") or ""
            domain_match = re.search(r"(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,63}", info, re.I)
            domain = domain_match.group(0).casefold().removeprefix("www.") if domain_match else None
            _record(rows, site, title, source_record_id=domain or title, domain=domain)
    elif group == "krybit":
        for card in driver.find_elements("css selector", ".post-card"):
            title = _optional(card, ".post-title")
            body = _text(card)
            domain_match = re.search(r"(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,63}", title or "", re.I)
            _record(rows, site, title, source_record_id=title,
                    domain=domain_match.group(0).casefold().removeprefix("www.") if domain_match else None)
            if rows and rows[-1]["organization"] == title:
                rows[-1]["source_publication_status"] = "published" if re.search(r"\bPUBLISHED\b", body, re.I) else None
    elif group == "netrunner_pr":
        for card in driver.find_elements("css selector", ".blog-item"):
            title = _optional(card, ".blog-item-title")
            domain = _optional(card, ".blog-item-info-website")
            country = _optional(card, ".blog-item-info-location")
            _record(rows, site, title, country, _optional(card, "time"),
                    source_record_id=domain or title, domain=domain)
    elif group == "notrace_group":
        for card in driver.find_elements("css selector", ".post.is-pending"):
            title = _optional(card, "h2,h3,h4")
            date_text = _optional(card, "time,.date,[class*='date']")
            _record(rows, site, title, listed_date=date_text, source_record_id=title)
            if rows and rows[-1]["organization"] == title:
                rows[-1]["source_publication_status"] = "yet_to_publish"
    elif group == "play_ransomware":
        for row in driver.find_elements("css selector", "table tr"):
            for card in row.find_elements("css selector", "th.News"):
                body = _text(card)
                parts = [part.strip() for part in body.split("|") if part.strip()]
                name = parts[0] if parts else None
                country = parts[1] if len(parts) > 1 else None
                domain_match = re.search(r"(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,63}", body, re.I)
                date_match = re.search(r"publication date:\s*(20\d{2}-\d{2}-\d{2})", body, re.I)
                _record(rows, site, name, country,
                        date_match.group(1) if date_match else None,
                        source_record_id=name,
                        domain=domain_match.group(0).casefold().removeprefix("www.") if domain_match else None)
    elif group == "sarcoma":
        for card in driver.find_elements("css selector", ".sg-form.card"):
            title = _optional(card, ".card-title")
            title = re.sub(r"^\d+\s+", "", title or "")
            body = _text(card)
            domain_match = re.search(r"\bSite:\s*((?:https?://)?(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,63})", body, re.I)
            country_match = re.search(r"\bGEO:\s*([^\r\n]+?)(?:\s+More info|$)", body, re.I)
            domain = domain_match.group(1) if domain_match else None
            if domain:
                domain = re.sub(r"^https?://", "", domain, flags=re.I).casefold().removeprefix("www.")
            _record(rows, site, title,
                    country_match.group(1).strip() if country_match else None,
                    source_record_id=domain or title, domain=domain)
    elif group == "apt73_bashe":
        for card in driver.find_elements("css selector", ".segment"):
            _record(rows, site, _optional(card, ".segment__text__off"),
                    _optional(card, ".segment__country__deadline"),
                    _optional(card, ".segment__date__deadline, .segment__date"))
    elif group == "arcus_media":
        for card in driver.find_elements("css selector", "article"):
            heading = _optional(card, "h2.entry-title, h2")
            _record(rows, site, heading, None, _optional(card, "time"))
    elif group == "barracuda":
        for card in driver.find_elements("css selector", ".grid .card"):
            _record(rows, site, _optional(card, "h3"), None, _optional(card, "time,.date"))
    elif group == "blackwater":
        for card in driver.find_elements("css selector", ".card"):
            _record(rows, site, _optional(card, ".card-title,h5"), None,
                    _optional(card, "time"))
    elif group == "cinder":
        for row in driver.find_elements("css selector", "table tr"):
            cells = row.find_elements("css selector", "td,th")
            if len(cells) >= 4 and cells[0].tag_name.lower() == "td":
                _record(rows, site, _text(cells[-1]))
    elif group == "cmd_organization":
        for card in driver.find_elements("css selector", ".item-card"):
            _record(rows, site, _optional(card, ".item-header"))
    elif group == "daixin_ransomware":
        for title in driver.find_elements("css selector", "h4.card-title"):
            name = _text(title)
            country = None
            match = re.search(r"\(([A-Z]{2,3}(?:\s*,\s*[A-Z]{2,3})*)\)\s*$", name)
            if match:
                country = match.group(1)
                name = name[:match.start()].strip()
            _record(rows, site, name, country)
    elif group == "doommageddon":
        for title in driver.find_elements("css selector", "main h2"):
            _record(rows, site, _text(title))
    elif group == "emperador":
        for card in driver.find_elements("css selector", ".card"):
            _record(rows, site, _optional(card, "h2,h3,h4,.card-title"))
    elif group == "endzone":
        for title in driver.find_elements("css selector", "h2.company-name"):
            _record(rows, site, _text(title))
    elif group == "falcon":
        for card in driver.find_elements("css selector", ".leak-entry"):
            _record(rows, site, _optional(card, ".leak-company"),
                    _optional(card, ".leak-country"),
                    _optional(card, "time,.leak-date"))
    elif group == "global_secret_group":
        for title in driver.find_elements("css selector", ".card-title"):
            _record(rows, site, _text(title))
    elif group == "karma_leaks":
        for card in driver.find_elements("css selector", ".card.card-compact"):
            listed_date = None
            for date_node in card.find_elements("css selector", "time,[data-created-at]"):
                date_value = (
                    date_node.get_attribute("datetime")
                    or date_node.get_attribute("data-created-at")
                    or _text(date_node)
                )
                date_match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", date_value)
                if date_match:
                    listed_date = date_match.group(0)
                    break
            _record(rows, site, _optional(card, "h3"),
                    _optional(card, ".country,.card-country"),
                    listed_date)
            # Date is often rendered as a bare span in the card header.
            if rows and not rows[-1]["listed_date"]:
                spans = card.find_elements("css selector", "span")
                for span in spans:
                    match = re.search(r"20\d{2}-\d{2}-\d{2}", _text(span))
                    if match and rows[-1]["organization"] == _optional(card, "h3"):
                        rows[-1]["listed_date"] = match.group(0)
                        break
    elif group == "qilin":
        for card in driver.find_elements("css selector", ".item_box"):
            title = card.find_elements("css selector", ".item_box-title[href]")
            if not title:
                continue
            href = title[0].get_attribute("href") or ""
            params = parse_qs(urlparse(href).query)
            record_id = (params.get("uuid") or [None])[0]
            date_text = None
            for item in card.find_elements("css selector", ".item_box-info__item"):
                candidate = _text(item)
                if re.fullmatch(r"[A-Z][a-z]{2} \d{1,2}, 20\d{2}", candidate, re.I):
                    date_text = candidate
                    break
            # Qilin's card date is its listing/post date, not proof that the
            # victim's files have been published. Publication is only confirmed
            # when the post itself contains the site's explicit "publicated" marker.
            post_text = _text(card)
            publicated = bool(re.search(r"\bpublicated\b", post_text, re.I))
            timer_nodes = card.find_elements("css selector", ".countdown-timer[data-remaining], .countdown-timer")
            remaining = None
            timer_raw = None
            if timer_nodes:
                timer_raw = _text(timer_nodes[0]) or None
                remaining_value = timer_nodes[0].get_attribute("data-remaining")
                try:
                    remaining = max(0, int(float(remaining_value))) if remaining_value else None
                except (TypeError, ValueError):
                    remaining = None
            company_link = card.find_elements("css selector", "a.item_box-info__link[href^='http']")
            domain = None
            if company_link:
                host = (urlparse(company_link[0].get_attribute("href") or "").hostname or "").casefold()
                host = host.removeprefix("www.")
                if re.fullmatch(
                    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
                    host,
                ):
                    domain = host
            before_count = len(rows)
            _record(rows, site, _optional(card, ".item_box-title"),
                    source_record_id=record_id, domain=domain, clear_leak_date=True)
            if len(rows) == before_count:
                continue
            row = rows[-1]
            row["source_created_at"] = date_text
            row["source_publication_status"] = "published" if publicated and remaining is None else "yet_to_publish"
            row["countdown_raw"] = timer_raw
            row["countdown_seconds_at_capture"] = remaining
            row["countdown_captured_at"] = datetime.now(timezone.utc).isoformat() if timer_nodes else None
            row["estimated_publish_at"] = (
                (datetime.now(timezone.utc) + timedelta(seconds=remaining)).isoformat()
                if remaining is not None else None
            )
    elif group == "kazu":
        # Read titles in one browser-side snapshot. Kazu's countdown script
        # updates its cards while Selenium iterates, which can stale element
        # references between calls.
        entries = driver.execute_script("""
            const capturedAt = new Date().toISOString();
            const timerSelector = '[data-countdown], [data-timer], [data-target], [data-deadline], [class*="countdown" i], [id*="countdown" i], [class*="timer" i], [id*="timer" i], [class*="deadline" i], [id*="deadline" i], .product-deadline, time';
            return [...document.querySelectorAll('#productList li')].map(item => {
              const nodes = [...item.querySelectorAll(timerSelector)].slice(0, 12);
              const countdown_candidates = nodes.map(node => ({
                text: (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim(),
                attributes: Object.fromEntries([...node.attributes]
                  .filter(attribute => /(count|timer|target|date|deadline|expire|publish|remain|time)/i.test(attribute.name))
                  .map(attribute => [attribute.name, attribute.value]))
              })).filter(candidate => candidate.text || Object.keys(candidate.attributes).length);
              const statusText = (item.innerText || '').toLowerCase();
              const source_publication_status = /\\b(published|released|leaked)\\b/.test(statusText) && !countdown_candidates.length
                ? 'published'
                : null;
              return {
                title: (item.querySelector('.product-item-title')?.innerText || '')
                  .replace(/\\s+/g, ' ').trim(),
                captured_at: capturedAt,
                countdown_candidates,
                source_publication_status
              };
            });
        """)
        for entry in entries:
            title = entry.get("title")
            original_title = title
            _, country = _strip_country_flag(title)
            # Kazu's displayed date is a countdown deadline for future
            # publication, not the date the victim was leaked.
            # Preserve the old identity derived from the original flag-prefixed
            # title so this correction updates observations instead of duping.
            before_count = len(rows)
            _record(
                rows,
                site,
                original_title,
                country,
                source_record_id=(original_title or "").casefold() or None,
                clear_leak_date=True,
            )
            if len(rows) > before_count:
                rows[-1].update(_parse_kazu_countdown(entry))
    elif group == "ms13_089_blog":
        for card in driver.find_elements("css selector", ".post"):
            name = _optional(card, ".post-title-block > div:first-child")
            country = None
            match = re.search(r"\(([^()]*)\)\s*$", name or "")
            if match:
                country = match.group(1)
                name = (name or "")[:match.start()].strip()
            _record(rows, site, name, country)
    elif group == "secp0":
        for card in driver.find_elements("css selector", ".post"):
            title = _optional(card, "h2")
            title = re.sub(r"^Leak:\s*", "", title or "", flags=re.I)
            _record(rows, site, title, None, _optional(card, "time,.date"))
    elif group == "vexy":
        for title in driver.find_elements("css selector", ".company-name"):
            _record(rows, site, _text(title))
    elif group == "unsafe":
        for card in driver.find_elements("css selector", ".reel"):
            title = _optional(card, ".reel-left h3")
            posted = None
            for paragraph in card.find_elements("css selector", ".reel-left p"):
                match = re.search(r"\bPosted:\s*(\d{1,2}/\d{1,2}/20\d{2})(?:,\s*(\d{1,2}:\d{2}:\d{2}\s*[AP]M))?", _text(paragraph), re.I)
                if match:
                    raw_date = match.group(1)
                    try:
                        posted = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
                    except ValueError:
                        pass
                    break
            parent_links = card.find_elements("xpath", "ancestor::a[contains(@class,'reel-link')]")
            href = parent_links[0].get_attribute("href") if parent_links else ""
            record_id = urlparse(href).path.rsplit("/", 1)[-1] or None
            domain_match = re.fullmatch(r"(?:www\.)?([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+)", title or "", re.I)
            domain = domain_match.group(1).casefold().removeprefix("www.") if domain_match else None
            _record(rows, site, title, listed_date=posted, source_record_id=record_id, domain=domain)

    return rows


def _collect_payload_listing(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Fetch Payload's server-rendered card list without waiting on its CSS assets."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    try:
        response = requests.get(
            site.url,
            proxies={"http": proxy, "https": proxy},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
            timeout=(20, 120),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"Payload listing request failed: {type(exc).__name__}: {str(exc)[:300]}"],
                "challenge": None}

    soup = BeautifulSoup(response.text, "html.parser")
    body_text = soup.get_text(" ", strip=True).casefold()
    challenge_marker = next((marker for marker in CHALLENGE_MARKERS if marker in body_text), None)
    if challenge_marker:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"challenge detected: {challenge_marker}"],
                "challenge": f"challenge detected: {challenge_marker}"}

    captured_at = datetime.now(timezone.utc)
    records = []
    for wrapper in soup.select("a.card-link"):
        card = wrapper.select_one("article.card")
        if not card:
            continue
        title_node = card.select_one(".title")
        raw_name = _text(title_node) if title_node else ""
        if not raw_name:
            continue
        title_domain = re.search(r"(?:\||·)\s*((?:[a-z0-9-]+\.)+[a-z]{2,})\b", raw_name, re.I)
        name = raw_name[:title_domain.start()].strip(" |·-") if title_domain else raw_name
        description = _text(card.select_one(".body")) if card.select_one(".body") else ""
        body_domain = re.search(r"\(([a-z0-9.-]+\.[a-z]{2,})\)", description, re.I)
        domain = (title_domain.group(1) if title_domain else body_domain.group(1) if body_domain else None)
        domain = domain.casefold().removeprefix("www.") if domain else None

        timer = card.select_one(".timer")
        timer_raw = _text(timer) if timer else None
        expired = bool(timer and "timer-expired" in timer.get("class", []))
        seconds = None
        deadline = None
        if timer_raw:
            duration = re.search(r"(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)?", timer_raw, re.I)
            if duration and any(duration.groups()):
                days, hours, minutes, secs = (int(value or 0) for value in duration.groups())
                seconds = days * 86400 + hours * 3600 + minutes * 60 + secs
                if seconds > 0:
                    deadline = captured_at + timedelta(seconds=seconds)
        status = "published" if expired or not seconds else "yet_to_publish"
        size = _text(card.select_one(".company-size")) if card.select_one(".company-size") else None
        source_url = urljoin(response.url, wrapper.get("href", ""))
        source_id = urlparse(source_url).path.rstrip("/").rsplit("/", 1)[-1] or name.casefold()
        date_match = re.search(r"\b(?:20\d{2}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3},?\s+20\d{2})\b", _text(card))
        listed_date = date_match.group(0) if date_match else None
        descriptions = [f"Data size: {size}"] if size else []
        record = {
            "organization": name,
            "country": None,
            "listed_date": listed_date,
            "source_created_at": None,
            "source_record_id": source_id,
            "domain": domain,
            "categories": [],
            "descriptions": descriptions,
            "source_publication_status": status,
            "estimated_publish_at": deadline.isoformat() if status == "yet_to_publish" and deadline else None,
            "countdown_captured_at": captured_at.isoformat() if status == "yet_to_publish" and timer_raw else None,
            "countdown_seconds_at_capture": seconds if status == "yet_to_publish" else None,
            "countdown_raw": timer_raw,
        }
        _record(records, site, name, listed_date=listed_date, source_record_id=source_id, domain=domain)
        if records and records[-1]["organization"].casefold() == name.casefold():
            records[-1].update(record)

    errors = [] if records else ["no Payload victim cards found in the server-rendered listing"]
    screenshot = b""
    dimensions = {}
    # The HTML is the source of record; capture a rendered proof image when the
    # headless browser is responsive, without allowing slow stylesheets to fail collection.
    driver = None
    try:
        driver = _make_driver(tor_host, tor_port)
        driver.set_page_load_timeout(20)
        driver.get(site.url)
        if driver.find_elements("css selector", "a.card-link article.card"):
            screenshot, dimensions = _screenshot(driver)
    except (TimeoutException, WebDriverException):
        pass
    finally:
        if driver:
            driver.quit()

    page = {
        "url": response.url,
        "title": soup.title.get_text(" ", strip=True) if soup.title else "Payload listing",
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "text/html"),
        "records": records,
        "response_metadata": {"date_inspection": inspect_markup_dates(response.text, records)},
        "screenshot": screenshot,
    }
    if screenshot:
        page.update({
            "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
            "screenshot_dimensions": dimensions,
        })
    return {"site": site, "pages": [page] if records else [], "pages_visited": 1,
            "errors": errors, "challenge": None}


def _collect_fulcrum_sec(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Fulcrum's victim cards use each company logo's alt text as its name."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    try:
        response = requests.get(
            site.url, proxies={"http": proxy, "https": proxy},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
            timeout=(45, 180),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"Fulcrum listing request failed: {type(exc).__name__}: {str(exc)[:300]}"],
                "challenge": None}

    soup = BeautifulSoup(response.text, "html.parser")
    records, seen = [], set()
    for image in soup.select("a.card img[alt]"):
        name = re.sub(r"\s+", " ", image.get("alt", "")).strip()
        if len(name) < 2:
            continue
        wrapper = image.find_parent("a", href=True)
        href = wrapper.get("href", "") if wrapper else ""
        source_id = urlparse(urljoin(response.url, href)).path.strip("/").split("/")[0] if href else name.casefold()
        source_id = source_id or name.casefold()
        if source_id.casefold() in seen:
            continue
        seen.add(source_id.casefold())
        _record(records, site, name, source_record_id=source_id)
    page = {
        "url": response.url,
        "title": soup.title.get_text(" ", strip=True) if soup.title else site.name,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "text/html"),
        "records": records,
        "response_metadata": {"collector": "image_alt_cards", "images_with_alt": len(soup.select("a.card img[alt]"))},
    }
    errors = [] if records else ["Fulcrum HTML contained no company names in image alt attributes"]
    return {"site": site, "pages": [page], "pages_visited": 1, "errors": errors, "challenge": None}


def _collect_run_some_wares(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Parse Run Some Wares' server-rendered cards; don't follow victim detail links."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    try:
        response = requests.get(
            site.url,
            proxies={"http": proxy, "https": proxy},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
            timeout=(45, 180),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"Run Some Wares listing request failed: {type(exc).__name__}: {str(exc)[:300]}"],
                "challenge": None}

    soup = BeautifulSoup(response.text, "html.parser")
    challenge = _source_challenge(soup.get_text(" ", strip=True))
    if challenge:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [challenge], "challenge": challenge}

    records = []
    for card in soup.select(".card"):
        title = card.select_one(".card-title")
        name = _text(title) if title else ""
        if not name:
            # Blank cards are image-based placeholders for paid/removed posts.
            continue
        logo = card.select_one(".card-logo")
        card_marker = str(logo.get("alt") or "").strip().casefold() if logo else ""
        if card_marker in {"paid", "deleted", "removed"}:
            continue
        detail = card.select_one("a.more-info-link[href]")
        detail_url = detail.get("href", "") if detail else ""
        parsed = urlparse(detail_url)
        source_id = parsed.path.strip("/") or None
        _record(records, site, name, source_record_id=source_id)

    page = {
        "url": response.url,
        "title": soup.title.get_text(" ", strip=True) if soup.title else site.name,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "text/html"),
        "records": records,
        "response_metadata": {"date_inspection": inspect_markup_dates(response.text, records)},
        "screenshot": b"",
    }
    errors = [] if records else ["no Run Some Wares victim cards matched"]
    return {"site": site, "pages": [page], "pages_visited": 1, "errors": errors, "challenge": None}


def _collect_sb_leaks(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Extract public listing names from SB Leaks while excluding warning posts."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    try:
        response = requests.get(
            site.url,
            proxies={"http": proxy, "https": proxy},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
            timeout=(20, 90),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"SB Leaks listing request failed: {type(exc).__name__}: {str(exc)[:300]}"],
                "challenge": None}

    soup = BeautifulSoup(response.text, "html.parser")
    challenge = _source_challenge(soup.get_text(" ", strip=True))
    if challenge:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [challenge], "challenge": challenge}

    records = []
    for heading in soup.select("h3"):
        name = _text(heading)
        if not name or name.casefold().startswith("warning:"):
            continue
        if name.casefold() in {"hall of shame", "sb leaks"}:
            continue
        parent = heading.parent
        date_node = parent.select_one("time[datetime], .date, .post-date") if parent else None
        listed_date = (date_node.get("datetime") or _text(date_node)) if date_node else None
        _record(records, site, name, listed_date=listed_date)

    page = {
        "url": response.url,
        "title": soup.title.get_text(" ", strip=True) if soup.title else site.name,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "text/html"),
        "records": records,
        "response_metadata": {"date_inspection": inspect_markup_dates(response.text, records)},
        "screenshot": b"",
    }
    errors = [] if records else ["no SB Leaks victim headings matched"]
    return {"site": site, "pages": [page], "pages_visited": 1, "errors": errors, "challenge": None}


def _collect_sarcoma(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Collect Sarcoma's 20-card pages through a headless browser session."""
    driver = _make_driver(tor_host, tor_port)
    # The source returns an empty response to generic clients, but serves the
    # listing to the Firefox UA used by the analyst's working browser.
    driver.execute_cdp_cmd("Network.setUserAgentOverride", {
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0"
    })
    driver.set_page_load_timeout(SLOW_HTML_SITE_PAGE_TIMEOUT_SECONDS)
    origin = f"{urlparse(site.url).scheme}://{urlparse(site.url).netloc}"
    queue = [site.url]
    visited: set[str] = set()
    pages = []
    errors = []
    challenge = None
    seen_source_ids: set[str] = set()

    try:
        while queue and len(visited) < MAX_PAGES_PER_SITE:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                driver.get(url)
                WebDriverWait(driver, 75).until(
                    lambda current: current.execute_script("return document.readyState") in ("interactive", "complete")
                )
                WebDriverWait(driver, 60).until(
                    lambda current: current.find_elements("css selector", ".sg-form.card")
                )
            except (TimeoutException, WebDriverException) as exc:
                errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:250]}")
                continue

            body = _text(driver.find_element("tag name", "body"))
            if "this page isn" in body.casefold() or "err_empty_response" in body.casefold():
                errors.append(f"{url}: browser received an empty server response")
                continue
            challenge = _source_challenge(body)
            if challenge:
                errors.append(challenge)
                break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            records = []
            for card in soup.select(".sg-form.card"):
                title_node = card.select_one(".card-title")
                raw_title = _text(title_node) if title_node else ""
                name = re.sub(r"^\d[\d,]*\s+", "", raw_title).strip()
                if not name:
                    continue

                fields = {}
                details = card.select_one(".card-text")
                if details:
                    for line in details.get_text("\n", strip=True).splitlines():
                        match = re.match(r"\s*(Site|Industry|GEO)\s*:\s*(.*?)\s*$", line, re.I)
                        if match and match.group(2):
                            fields[match.group(1).casefold()] = match.group(2).strip()

                website = fields.get("site")
                domain = None
                if website:
                    parsed = urlsplit(website if "://" in website else f"//{website}")
                    domain = (parsed.hostname or "").casefold().removeprefix("www.") or None
                industry = fields.get("industry")
                country = fields.get("geo")
                button = card.select_one("button.company_button[data-bs-target]")
                modal_id = (button.get("data-bs-target", "") if button else "").removeprefix("#")

                # The listing contains one obvious template card with the
                # literal organization/domain/industry "Victim"; discard it.
                if name.casefold() == "victim" and domain == "victim.com" and (industry or "").casefold() == "victim":
                    continue
                if modal_id and modal_id in seen_source_ids:
                    continue
                source_id = modal_id or domain or name.casefold()
                if source_id in seen_source_ids:
                    continue
                seen_source_ids.add(source_id)
                _record(records, site, name, country=country, source_record_id=source_id, domain=domain)
                if records and records[-1]["organization"].casefold() == name.casefold():
                    records[-1]["categories"] = [industry] if industry else []
                    records[-1]["descriptions"] = []

            screenshot, screenshot_dimensions = _screenshot(driver) if not pages else (b"", {})
            page = {
                "url": driver.current_url,
                "title": driver.title or site.name,
                "status_code": 200,
                "content_type": "text/html",
                "records": records,
                "response_metadata": {"date_inspection": inspect_markup_dates(driver.page_source, records)},
                "screenshot": screenshot,
            }
            if page["screenshot"]:
                page["screenshot_sha256"] = hashlib.sha256(page["screenshot"]).hexdigest()
                page["screenshot_dimensions"] = screenshot_dimensions
            pages.append(page)

            for anchor in soup.select("a[href]"):
                href = urldefrag(urljoin(driver.current_url, anchor.get("href", "")))[0]
                parsed = urlparse(href)
                query = parse_qs(parsed.query)
                page_values = query.get("page", [])
                if page_values == ["1"] and parsed.path == urlparse(site.url).path:
                    continue
                if (
                    f"{parsed.scheme}://{parsed.netloc}".casefold() == origin.casefold()
                    and page_values and page_values[0].isdigit()
                    and href not in visited and href not in queue
                    and len(visited) + len(queue) < MAX_PAGES_PER_SITE
                ):
                    queue.append(href)

    finally:
        driver.quit()

    if queue:
        errors.append(f"Sarcoma pagination reached the {MAX_PAGES_PER_SITE}-page safety limit")
    if not any(page["records"] for page in pages) and not errors and not challenge:
        errors.append("no Sarcoma victim cards matched")
    return {"site": site, "pages": pages, "pages_visited": len(pages), "errors": errors, "challenge": challenge}


def _collect_pear(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Collect PEAR's current listing and its static All Leaks archive."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    mirrors = [
        "http://peargxn3oki34c4savcbcfqofjjwjnnyrlrbszfv6ujlx36mhrh57did.onion/",
        "http://pearsmob5sn44ismokiusuld34pnfwi6ctgin3qbvonpoob4lh3rmtqd.onion/",
    ]
    errors = []
    for base_url in mirrors:
        pages = []
        seen_ids: set[str] = set()
        try:
            for path in ("", "All%20Leaks/"):
                url = urljoin(base_url, path)
                response = requests.get(
                    url,
                    proxies={"http": proxy, "https": proxy},
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
                    timeout=(30, 180),
                )
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")
                body_text = soup.get_text(" ", strip=True)
                challenge = _source_challenge(body_text)
                if challenge:
                    return {"site": site, "pages": [], "pages_visited": len(pages) + 1,
                            "errors": [challenge], "challenge": challenge}

                records = []
                for detail_link in soup.select('a[href^="Companies/"]'):
                    card = detail_link.find_parent("td", class_="es-text-7589")
                    if card is None:
                        continue
                    title = card.find("p")
                    title_strong = title.find("strong") if title else None
                    raw_name = title_strong.get_text(" ", strip=True) if title_strong else ""
                    raw_name = re.sub(r"[\U0001F1E6-\U0001F1FF]{2}", "", raw_name).strip()
                    name, flag_country = _strip_country_flag(raw_name)
                    if not name:
                        continue
                    record_id = urlparse(detail_link.get("href", "")).path.rstrip("/").rsplit("/", 1)[-1]
                    if not record_id:
                        record_id = name.casefold()
                    if record_id in seen_ids:
                        continue
                    seen_ids.add(record_id)

                    status_node = title.find("mark") if title else None
                    raw_status = _text(status_node).casefold() if status_node else ""
                    if raw_status == "announced":
                        publication_status = "yet_to_publish"
                    elif raw_status in {"leaked", "samples posted", "published", "exposed"}:
                        publication_status = "published"
                    else:
                        publication_status = None

                    paragraphs = card.find_all("p", recursive=False)
                    summary = paragraphs[1].get_text(" ", strip=True) if len(paragraphs) > 1 else ""
                    fields: dict[str, str] = {}
                    for paragraph in card.select(".info__body p"):
                        label_node = paragraph.find("strong")
                        if not label_node:
                            continue
                        label = label_node.get_text(" ", strip=True).rstrip(":").casefold()
                        value = paragraph.get_text(" ", strip=True)
                        value = re.sub(rf"^{re.escape(label_node.get_text(' ', strip=True))}\s*", "", value, flags=re.I).strip()
                        if label and value and label not in {"details"}:
                            fields[label] = value

                    site_anchor = next(
                        (p.select_one("a[href]") for p in card.select(".info__body p")
                         if (p.find("strong") and p.find("strong").get_text(" ", strip=True).rstrip(":").casefold() == "site")),
                        None,
                    )
                    raw_domain = (site_anchor.get("href") if site_anchor else "") or fields.get("site", "")
                    parsed_domain = urlsplit(raw_domain if "://" in raw_domain else f"//{raw_domain}")
                    domain = (parsed_domain.hostname or "").casefold().removeprefix("www.") or None
                    country_value = re.sub(r"\s*\U0001f4cd.*$", "", fields.get("location", "")).strip()
                    country_aliases = {"usa": "United States", "us": "United States", "uk": "United Kingdom"}
                    country = country_aliases.get(country_value.casefold(), country_value) or flag_country
                    notified = re.sub(r"\s*\U0001f514.*$", "", fields.get("date company notified", "")).strip()
                    details = [summary] if summary else []
                    data_volume = " ".join(paragraphs[2].get_text(" ", strip=True).split()) if len(paragraphs) > 2 else ""
                    data_volume = re.sub(r"^Data Volume:\s*", "", data_volume, flags=re.I).strip()
                    if data_volume:
                        details.append(f"Data volume: {data_volume}")
                    if notified:
                        details.append(f"Company notified: {notified}")
                    if fields.get("industry"):
                        details.append(f"Industry: {fields['industry']}")
                    if fields.get("revenue"):
                        details.append(f"Revenue: {fields['revenue']}")
                    details.append(f"Listing status: {raw_status or 'not stated'}")
                    records.append({
                        "organization": name,
                        "country": country,
                        "listed_date": None,
                        "source_created_at": None,
                        "source_record_id": record_id,
                        "domain": domain,
                        "categories": [fields["industry"]] if fields.get("industry") else [],
                        "descriptions": details,
                        "source_publication_status": publication_status,
                    })

                pages.append({
                    "url": response.url,
                    "title": soup.title.get_text(" ", strip=True) if soup.title else site.name,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", "text/html"),
                    "records": records,
                    "response_metadata": {
                        "listing_type": "current" if not path else "all_leaks_archive",
                        "records_extracted": len(records),
                        "date_semantics": "Company notified date is retained in description; not treated as leak date.",
                    },
                    "screenshot": b"",
                })
            if any(page["records"] for page in pages):
                errors = []
                break
            errors.append(f"PEAR returned no victim entries from mirror {base_url}")
        except requests.RequestException as exc:
            errors.append(f"PEAR request failed for {base_url}: {type(exc).__name__}: {str(exc)[:250]}")

    if not any(page.get("records") for page in pages):
        return {"site": site, "pages": [], "pages_visited": len(pages), "errors": errors or ["no PEAR victim cards matched"], "challenge": None}
    return {"site": site, "pages": pages, "pages_visited": len(pages), "errors": errors, "challenge": None}


def _collect_toufan_leaks(site: HtmlLeakSite) -> dict:
    """Parse WordPress archive cards, dates, and the site's paged archive links."""
    pages, errors, seen = [], [], set()
    try:
        for page_number in range(1, MAX_PAGES_PER_SITE + 1):
            url = site.url if page_number == 1 else f"{site.url}?paged={page_number}"
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
                timeout=(15, 45),
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            posts = soup.select("article.content-area div.post")
            records = []
            for post in posts:
                title_link = next((a for a in post.select('a[href*="?p="]') if a.get_text(" ", strip=True)), None)
                if title_link is None:
                    continue
                raw_title = re.sub(r"\s+", " ", title_link.get_text(" ", strip=True)).strip()
                if not raw_title:
                    continue
                if re.match(r"^Operation\b", raw_title, re.I):
                    name = raw_title.rsplit(":", 1)[-1].strip()
                else:
                    name = re.sub(r"^ILDefenseLeaks\s*:\s*", "", raw_title, flags=re.I).strip()
                name = re.sub(
                    r"\s+[–—-]\s+[\"'“”]?(?:(?:https?://)?(?:www\.)?)[a-z0-9.-]+\.[a-z]{2,}[\"'“”]?\s*$",
                    "", name, flags=re.I,
                ).strip(" \t-|–—:()\"'“”")
                metadata = post.select_one(".metadata")
                date_text = metadata.get_text(" ", strip=True) if metadata else ""
                parsed_date = None
                for date_format in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
                    try:
                        parsed_date = datetime.strptime(date_text, date_format).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
                listed_date = parsed_date.isoformat() if parsed_date else None
                post_id_match = re.search(r"\bpost-(\d+)\b", " ".join(post.get("class", [])))
                source_id = post_id_match.group(1) if post_id_match else title_link.get("href")
                source_id = str(source_id)
                if source_id in seen:
                    continue
                seen.add(source_id)
                domain_match = re.search(r"(?:https?://)?(?:www\.)?([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,})(?:/|\b)", raw_title, re.I)
                domain = domain_match.group(1).casefold().removeprefix("www.") if domain_match else None
                if domain and name.casefold() == domain.casefold():
                    name = domain
                _record(records, site, name, listed_date=listed_date, source_record_id=source_id, domain=domain)
            pages.append({
                "url": response.url,
                "title": soup.title.get_text(" ", strip=True) if soup.title else site.name,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", "text/html"),
                "records": records,
                "response_metadata": {"page": page_number, "posts_found": len(posts)},
            })
            if not soup.select_one(f'a[href*="paged={page_number + 1}"]'):
                break
    except (requests.RequestException, ValueError) as exc:
        errors.append(f"Toufan archive request failed: {type(exc).__name__}: {str(exc)[:300]}")
    if pages and not any(page["records"] for page in pages):
        errors.append("Toufan archive pages contained no parseable victim titles")
    return {"site": site, "pages": pages, "pages_visited": len(pages), "errors": errors, "challenge": None}


def _collect_leakeddata(site: HtmlLeakSite) -> dict:
    """Read LeakedData's table cards from /about/ without following download links."""
    try:
        response = requests.get(
            site.url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
            timeout=(20, 180),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"LeakedData listing request failed: {type(exc).__name__}: {str(exc)[:300]}"],
                "challenge": None}

    soup = BeautifulSoup(response.text, "html.parser")
    records, seen = [], set()
    table_count = 0
    for table in soup.select("table"):
        fields = {}
        for row in table.select("tr"):
            cells = row.select("th, td")
            if len(cells) < 2:
                continue
            label = re.sub(r"\s+", " ", cells[0].get_text(" ", strip=True)).strip().rstrip(":").casefold()
            if label:
                fields[label] = re.sub(r"\s+", " ", cells[1].get_text(" ", strip=True)).strip()
        name = fields.get("company")
        if not name:
            continue
        table_count += 1
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        _record(records, site, name, source_record_id=key)
        status = fields.get("status", "").casefold()
        if records and records[-1]["organization"].casefold() == key:
            records[-1]["source_publication_status"] = "published" if "leak" in status else None
    page = {
        "url": response.url,
        "title": soup.title.get_text(" ", strip=True) if soup.title else site.name,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "text/html"),
        "records": records,
        "response_metadata": {"collector": "table_cards", "company_tables": table_count},
    }
    errors = [] if records else ["LeakedData about page contained no company tables"]
    return {"site": site, "pages": [page], "pages_visited": 1, "errors": errors, "challenge": None}


def _collect_ransomexx_v2(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Parse RansomEXX's dated static HTML lists and follow indexN.html pages."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    session = requests.Session()
    session.trust_env = False
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"})
    pages, errors, seen_urls, seen_ids = [], [], set(), set()
    country_names = {
        "usa": "United States", "uk": "United Kingdom", "uae": "United Arab Emirates",
        "hongkong": "Hong Kong", "saudi": "Saudi Arabia",
        "trinidad-and-tobago": "Trinidad and Tobago",
    }
    url = site.url
    try:
        for page_number in range(1, MAX_PAGES_PER_SITE + 1):
            if url in seen_urls:
                break
            seen_urls.add(url)
            response = session.get(url, timeout=(45, 180))
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            listing = soup.find("ol")
            items = listing.find_all("li", recursive=False) if listing else []
            records = []
            for item in items:
                heading = item.select_one("h4")
                title_link = heading.select_one("a[href]") if heading else None
                raw_name = (title_link or heading).get_text(" ", strip=True) if heading else ""
                if not raw_name:
                    continue
                name = re.sub(r"\s+", " ", raw_name).strip()
                permalink = title_link.get("href") if title_link else ""
                record_id = urlparse(urljoin(response.url, permalink)).path.strip("/") if permalink else name.casefold()
                if not record_id or record_id in seen_ids:
                    continue
                seen_ids.add(record_id)

                item_text = item.get_text(" ", strip=True)
                date_match = re.search(r"\bDate:\s*((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d{1,2}\s+[A-Za-z]+\s+\d{4})", item_text, re.I)
                listed_date = None
                if date_match:
                    for date_format in ("%a %d %B %Y", "%a %d %b %Y"):
                        try:
                            listed_date = datetime.strptime(date_match.group(1), date_format).replace(tzinfo=timezone.utc).isoformat()
                            break
                        except ValueError:
                            continue

                tags = [a.get_text(" ", strip=True).strip().lstrip("#").casefold() for a in item.select('a[href*="/tag/"]')]
                country_tag = next((tag for tag in tags if tag), None)
                country = country_names.get(country_tag, country_tag.replace("-", " ").title()) if country_tag else None

                domain_match = re.search(r"\(([a-z0-9.-]+\.[a-z]{2,})\)", name, re.I)
                if not domain_match and re.fullmatch(r"(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,}", name, re.I):
                    domain_match = re.fullmatch(r"(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})", name, re.I)
                domain = domain_match.group(1).casefold().removeprefix("www.") if domain_match else None
                _record(records, site, name, country=country, listed_date=listed_date,
                        source_record_id=record_id, domain=domain)

            next_link = next((a for a in soup.select("a[href]") if a.get_text(" ", strip=True) == "⇨"), None)
            pages.append({
                "url": response.url,
                "title": soup.title.get_text(" ", strip=True) if soup.title else site.name,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", "text/html"),
                "records": records,
                "response_metadata": {"page": page_number, "listing_items": len(items)},
            })
            if not next_link:
                break
            url = urljoin(response.url, next_link.get("href", ""))
        else:
            errors.append(f"RansomEXX pagination stopped at safety limit ({MAX_PAGES_PER_SITE} pages)")
    except requests.RequestException as exc:
        errors.append(f"RansomEXX listing request failed: {type(exc).__name__}: {str(exc)[:300]}")
    finally:
        session.close()
    if pages and not any(page["records"] for page in pages):
        errors.append("RansomEXX pages contained no parseable victim entries")
    return {"site": site, "pages": pages, "pages_visited": len(pages), "errors": errors, "challenge": None}


def _collect_beast_listing(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Collect Beast's server-rendered catalog without opening victim detail links."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    session = requests.Session()
    session.trust_env = False
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })

    queue, visited, pages, errors = [site.url], set(), [], []
    origin = urlparse(site.url).netloc.casefold()
    challenge = None
    while queue and len(visited) < 20:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            response = session.get(url, timeout=(45, 180), allow_redirects=True)
            if response.status_code == 304:
                response = session.get(
                    url,
                    headers={"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"},
                    timeout=(45, 180), allow_redirects=True,
                )
            if response.status_code == 304:
                errors.append(f"{url}: server returned 304 without a cached response body")
                continue
            response.raise_for_status()
        except requests.RequestException as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:350]}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        challenge = _source_challenge(soup.get_text(" ", strip=True))
        if challenge:
            errors.append(challenge)
            break

        records = []
        for card in soup.select(".catalog > a.card[href]"):
            title_node = card.select_one(".card-head h3")
            title = _text(title_node) if title_node else ""
            if len(title) < 2:
                continue
            info = {}
            for item in card.select(".card-info > div"):
                match = re.match(r"\s*([^:]+):\s*(.*?)\s*$", _text(item))
                if match:
                    info[match.group(1).casefold()] = match.group(2)

            raw_date = info.get("date")
            listed_date = None
            if raw_date:
                try:
                    date_format = "%Y.%m.%d" if re.match(r"^20\d{2}[./-]", raw_date) else "%d.%m.%Y"
                    listed_date = datetime.strptime(raw_date.replace("/", ".").replace("-", "."), date_format).date().isoformat()
                except ValueError:
                    pass

            timer_node = card.select_one(".card-counter .timer")
            timer_raw = _text(timer_node) if timer_node else ""
            normalized_timer = re.sub(r"\s+", "", timer_raw).casefold()
            counter = card.select_one(".card-counter[data-date]")
            deadline = _parse_datetime(counter.get("data-date")) if counter else None
            unpublished = bool(card.select_one(".card-info .unpublished"))
            if "published" in normalized_timer or "leaked" in normalized_timer:
                publication_status = "published"
            elif deadline and deadline > datetime.now(timezone.utc):
                publication_status = "yet_to_publish"
            elif deadline:
                publication_status = "published"
            elif unpublished:
                publication_status = "yet_to_publish"
            else:
                publication_status = None

            website = info.get("website", "").casefold().removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/")
            if not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", website):
                website = None
            source_id = urlparse(card.get("href", "")).path.rstrip("/").rsplit("/", 1)[-1] or title.casefold()
            _record(records, site, title, listed_date=listed_date, source_record_id=source_id, domain=website)
            if not records or records[-1]["organization"].casefold() != title.casefold():
                continue
            captured_at = datetime.now(timezone.utc)
            seconds = max(0, int((deadline - captured_at).total_seconds())) if deadline and publication_status == "yet_to_publish" else None
            description_node = card.select_one(".card-text")
            description_text = description_node.get_text(" ", strip=True) if description_node else ""
            descriptions = [re.sub(r"\s+", " ", description_text).strip()] if description_text else []
            for label in ("revenue", "data size"):
                value = info.get(label)
                if value and value != "-":
                    descriptions.append(f"{label.title()}: {value}")
            records[-1].update({
                "source_publication_status": publication_status,
                "estimated_publish_at": deadline.isoformat() if deadline and publication_status == "yet_to_publish" else None,
                "countdown_captured_at": captured_at.isoformat() if deadline and publication_status == "yet_to_publish" else None,
                "countdown_seconds_at_capture": seconds,
                "countdown_raw": timer_raw or None,
                "descriptions": descriptions,
            })

        page_url = response.url
        screenshot, dimensions = _capture_listing_screenshot(page_url, tor_host, tor_port, ".catalog > a.card")
        page = {
            "url": page_url,
            "title": soup.title.get_text(" ", strip=True) if soup.title else "Beast Leaks",
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "text/html"),
            "records": records,
            "response_metadata": {
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
                "date_inspection": inspect_markup_dates(response.text, records),
            },
            "screenshot": screenshot,
        }
        if screenshot:
            page.update({"screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                         "screenshot_dimensions": dimensions})
        pages.append(page)

        for anchor in soup.select(".pagination a[href], nav.pagination a[href], .pages a[href]"):
            next_url = urljoin(page_url, anchor.get("href", ""))
            if urlparse(next_url).netloc.casefold() != origin:
                continue
            if next_url not in visited and next_url not in queue:
                queue.append(next_url)

    session.close()
    if len(visited) >= 20 and queue:
        errors.append("Beast Leaks pagination stopped at the 20-page safety limit")
    if not any(page["records"] for page in pages) and not challenge and not errors:
        errors.append("no Beast Leaks cards matched `.catalog > a.card`")
    return {"site": site, "pages": pages, "pages_visited": len(pages), "errors": errors, "challenge": challenge}


def _collect_blackout_listing(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Parse Blackout's public company-card listing; do not follow post links."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    session = requests.Session()
    session.trust_env = False
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })

    response = None
    request_error = None
    for attempt in range(2):
        try:
            response = session.get(site.url, timeout=(90, 240), allow_redirects=True)
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            request_error = exc
            if attempt == 0:
                time.sleep(1)
    if response is None:
        session.close()
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"Blackout listing request failed after retry: {type(request_error).__name__}: {str(request_error)[:350]}"],
                "challenge": None}

    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select(".company-cards-wrapper > .card")
    # The listing is the ground truth when cards exist. Gateway/challenge
    # wording elsewhere in the page must not cause a false CAPTCHA result.
    if not cards:
        challenge = _source_challenge(soup.get_text(" ", strip=True))
        if challenge or urlparse(response.url).path.rstrip("/").endswith("/b/challenge"):
            session.close()
            challenge = challenge or "challenge detected: Blackout Gateway verification page"
            return {"site": site, "pages": [], "pages_visited": 1,
                    "errors": [challenge], "challenge": challenge}

    records = []
    for card in cards:
        title_node = card.select_one(".card-title a")
        name = _text(title_node) if title_node else ""
        if not name:
            continue
        post_url = urljoin(response.url, title_node.get("href", ""))
        post_id = urlparse(post_url).path.strip("/").rsplit("/", 1)[-1] or name.casefold()
        domain_candidate = name.casefold().removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/")
        domain = domain_candidate if re.fullmatch(
            r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
            domain_candidate,
        ) else None
        country_node = card.select_one(".country, [data-country]")
        country = (country_node.get("data-country") or _text(country_node)) if country_node else None
        summary_node = card.select_one(".card-text")
        description = _text(summary_node) if summary_node else None
        footer = card.select_one(".card-footer")
        status_text = _text(footer).casefold() if footer else ""
        if re.search(r"\b(published|leaked|exposed)\b", status_text):
            publication_status = "published"
        elif re.search(r"\b(pending|unpublished|awaiting|not published)\b", status_text):
            publication_status = "yet_to_publish"
        else:
            publication_status = None
        date_node = card.select_one("time[datetime], [data-date], [datetime]")
        raw_date = (date_node.get("datetime") or date_node.get("data-date") or _text(date_node)) if date_node else None
        listed_date = None
        if raw_date:
            parsed_date = _parse_datetime(raw_date)
            if parsed_date:
                listed_date = parsed_date.isoformat()
            else:
                listed_date = _parse_date(raw_date).isoformat() if _parse_date(raw_date) else None

        _record(records, site, name, country=country, listed_date=listed_date,
                source_record_id=post_id, domain=domain)
        if records and records[-1]["organization"].casefold() == name.casefold():
            records[-1].update({
                "source_publication_status": publication_status,
                "descriptions": [description] if description else [],
            })

    screenshot = b""
    dimensions = {}
    if records:
        driver = None
        try:
            driver = _make_driver(tor_host, tor_port)
            driver.set_page_load_timeout(90)
            driver.get(response.url)
            WebDriverWait(driver, 15).until(
                lambda current: current.find_elements("css selector", ".company-cards-wrapper > .card")
            )
            screenshot, dimensions = _screenshot(driver)
        except (TimeoutException, WebDriverException):
            pass
        finally:
            if driver:
                driver.quit()

    page = {
        "url": response.url,
        "title": soup.title.get_text(" ", strip=True) if soup.title else "Blackout",
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "text/html"),
        "records": records,
        "response_metadata": {
            "date_inspection": inspect_markup_dates(response.text, records),
        },
        "screenshot": screenshot,
    }
    if screenshot:
        page.update({"screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                     "screenshot_dimensions": dimensions})

    # Only follow explicit pagination controls. Card links lead to individual
    # posts and are intentionally not crawled.
    pages = [page] if records else []
    errors = []
    for anchor in soup.select(".pagination a[href], nav[aria-label*='pagination' i] a[href], .page-item a[href]"):
        next_url = urljoin(response.url, anchor.get("href", ""))
        if urlparse(next_url).netloc.casefold() != urlparse(site.url).netloc.casefold():
            continue
        if next_url == response.url:
            continue
        try:
            next_response = session.get(next_url, timeout=(90, 240), allow_redirects=True)
            next_response.raise_for_status()
            next_soup = BeautifulSoup(next_response.text, "html.parser")
            next_cards = next_soup.select(".company-cards-wrapper > .card")
            next_records = []
            for card in next_cards:
                title_node = card.select_one(".card-title a")
                name = _text(title_node) if title_node else ""
                if not name:
                    continue
                post_id = urlparse(urljoin(next_response.url, title_node.get("href", ""))).path.strip("/").rsplit("/", 1)[-1] or name.casefold()
                domain_candidate = name.casefold().removeprefix("www.").rstrip("/")
                domain = domain_candidate if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,63}", domain_candidate) else None
                footer = card.select_one(".card-footer")
                status_text = _text(footer).casefold() if footer else ""
                publication_status = "published" if re.search(r"\b(published|leaked|exposed)\b", status_text) else "yet_to_publish" if re.search(r"\b(pending|unpublished|awaiting)\b", status_text) else None
                summary = card.select_one(".card-text")
                _record(next_records, site, name, source_record_id=post_id, domain=domain)
                if next_records and next_records[-1]["organization"].casefold() == name.casefold():
                    next_records[-1].update({"source_publication_status": publication_status,
                                             "descriptions": [_text(summary)] if summary else []})
            if next_records:
                pages.append({"url": next_response.url,
                              "title": next_soup.title.get_text(" ", strip=True) if next_soup.title else "Blackout",
                              "status_code": next_response.status_code,
                              "content_type": next_response.headers.get("content-type", "text/html"),
                              "records": next_records,
                              "response_metadata": {"date_inspection": inspect_markup_dates(next_response.text, next_records)},
                              "screenshot": b""})
        except requests.RequestException as exc:
            errors.append(f"Blackout pagination {next_url} failed: {type(exc).__name__}: {str(exc)[:250]}")

    session.close()
    if not records and not errors:
        errors.append("no Blackout listing cards matched `.company-cards-wrapper > .card`")
    return {"site": site, "pages": pages, "pages_visited": len(pages) or 1,
            "errors": errors, "challenge": None}


def _pagination_links(driver, origin: str) -> list[str]:
    boxes = driver.find_elements(
        "css selector",
        "nav[aria-label*='pagination' i],.pagination,.pager,[class*='pagination']",
    )
    links = [a for box in boxes for a in box.find_elements("css selector", "a[href]")]
    links += driver.find_elements("css selector", "a[rel~='next'][href]")
    links += driver.find_elements("css selector", "a[href*='/page/']")
    found = []
    for link in links:
        href = link.get_attribute("href")
        if not href or urlparse(href).netloc.lower() != urlparse(origin).netloc.lower():
            continue
        label = f"{_text(link)} {link.get_attribute('rel') or ''}".lower()
        if any(token in label for token in ("next", "older", "›", "»", "→")) or _text(link).isdigit():
            found.append(href)
    return list(dict.fromkeys(found))


def _screenshot(driver) -> tuple[bytes, dict]:
    try:
        metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
        size = metrics.get("cssContentSize", {})
        width = min(max(int(size.get("width", 1440)), 900), 2400)
        height = min(max(int(size.get("height", 1200)), 1200), 14000)
        captured = driver.execute_cdp_cmd("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": True,
            "fromSurface": True,
            "clip": {"x": 0, "y": 0, "width": width, "height": height, "scale": 1},
        })
        data = base64.b64decode(captured["data"])
        return data, {"width": width, "height": height, "full_page": True}
    except Exception:
        return driver.get_screenshot_as_png(), {"full_page": False}


def _collect_play_site_pages(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Collect Play's server-rendered listing cards without opening details."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    session = requests.Session()
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    })
    queue, visited, pages, errors = [site.url], set(), [], []
    origin = urlparse(site.url).netloc.casefold()
    challenge = None
    while queue and len(visited) < MAX_PAGES_PER_SITE:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            response = session.get(url, timeout=(15, 45))
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            body_text = soup.get_text(" ", strip=True).casefold()
            marker = next((value for value in CHALLENGE_MARKERS if value in body_text), None)
            if marker:
                challenge = f"challenge detected: {marker}"
                break
            records = []
            for cell in soup.select("th.News"):
                text = _text(cell)
                parts = [part.strip() for part in text.split("|") if part.strip()]
                if not parts:
                    continue
                name = parts[0]
                country = parts[1] if len(parts) > 1 else None
                domain_match = re.search(r"(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,63}", text, re.I)
                date_match = re.search(r"publication date:\s*(20\d{2}-\d{2}-\d{2})", text, re.I)
                _record(
                    records,
                    site,
                    name,
                    country,
                    date_match.group(1) if date_match else None,
                    source_record_id=name,
                    domain=domain_match.group(0).casefold().removeprefix("www.") if domain_match else None,
                )
            date_inspection = inspect_markup_dates(response.text, records)
            pages.append({
                "url": response.url,
                "title": soup.title.get_text(" ", strip=True) if soup.title else None,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", "text/html"),
                "records": records,
                "screenshot": b"",
                "response_metadata": {"collector": "server_rendered_listing", "date_inspection": date_inspection},
            })
            for anchor in soup.select("a[href]"):
                label = _text(anchor).casefold()
                href = urljoin(response.url, anchor.get("href", ""))
                parsed = urlparse(href)
                page_number = parse_qs(parsed.query).get("page", [])
                if (
                    parsed.netloc.casefold() == origin
                    and parsed.path.casefold().endswith("index.php")
                    and page_number
                    and page_number[0].isdigit()
                    and (label.isdigit() or any(token in label for token in ("next", "older", "»", "›")))
                    and href not in visited
                    and href not in queue
                    and len(visited) + len(queue) < MAX_PAGES_PER_SITE
                ):
                    queue.append(href)
        except requests.RequestException as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:350]}")
            break
    if not any(page.get("records") for page in pages) and not challenge and not errors:
        errors.append("no victim records matched the server-rendered listing cards")
    return {"site": site, "pages": pages, "pages_visited": len(visited), "errors": errors, "challenge": challenge}


def _make_driver(
    tor_host: str,
    tor_port: int,
    ignore_certificate_errors: bool = False,
    page_load_timeout: int = PAGE_TIMEOUT_SECONDS,
    webdriver_command_timeout: int = 120,
) -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(f"--proxy-server=socks5://{tor_host}:{tor_port}")
    options.add_argument("--proxy-bypass-list=<-loopback>")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1440,1200")
    if ignore_certificate_errors:
        options.add_argument("--ignore-certificate-errors")
    options.page_load_strategy = "eager"
    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    })
    driver = webdriver.Chrome(options=options)
    # Selenium's HTTP command timeout defaults to 120s independently of the
    # browser's page-load timeout. Slow Tor sources such as Anubis need both.
    driver.command_executor._client_config.timeout = webdriver_command_timeout
    driver.set_page_load_timeout(page_load_timeout)
    driver.set_script_timeout(max(25, min(page_load_timeout, 60)))
    return driver


def _capture_listing_screenshot(url: str, tor_host: str, tor_port: int, selector: str) -> tuple[bytes, dict]:
    """Capture a best-effort screenshot without making rendered UI a scrape dependency."""
    driver = None
    try:
        driver = _make_driver(tor_host, tor_port)
        driver.set_page_load_timeout(18)
        driver.get(url)
        try:
            WebDriverWait(driver, 10).until(
                lambda current: current.find_elements("css selector", selector)
            )
        except TimeoutException:
            pass
        return _screenshot(driver)
    except WebDriverException:
        return b"", {}
    finally:
        if driver:
            try:
                driver.quit()
            except WebDriverException:
                pass


def _source_challenge(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", text).casefold()
    for marker in ("verify you are human", "checking your browser", "proof of work",
                   "captcha verification", "complete the captcha to continue"):
        if marker in normalized:
            return f"challenge detected: {marker}"
    return None


def _collect_rhysida_listing(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Read Rhysida's public archive list; never request company detail or file links."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    archive_url = urljoin(site.url, "archive.php")
    try:
        response = requests.get(
            archive_url,
            proxies={"http": proxy, "https": proxy},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
            timeout=(20, 60),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"Rhysida archive request failed: {type(exc).__name__}: {str(exc)[:300]}"],
                "challenge": None}

    soup = BeautifulSoup(response.text, "html.parser")
    challenge = _source_challenge(soup.get_text(" ", strip=True))
    if challenge:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [challenge], "challenge": challenge}

    records = []
    for button in soup.select("button[data-company]"):
        card = button.find_parent("div", class_="border")
        if not card:
            continue
        title = card.select_one(".h4 a[href]")
        name = _text(title) if title else ""
        if not name:
            continue

        domain = None
        if title:
            candidate_host = (urlparse(title.get("href", "")).hostname or "").casefold()
            if candidate_host and not candidate_host.endswith(".onion"):
                domain = candidate_host.removeprefix("www.")

        progress = card.select_one(".progress-bar[aria-valuenow], .progress-bar")
        progress_value = None
        if progress:
            raw_progress = progress.get("aria-valuenow") or _text(progress)
            match = re.search(r"\b(\d{1,3})\s*%?\b", raw_progress)
            if match:
                progress_value = min(100, int(match.group(1)))

        card_text = _text(card)
        metadata = []
        size_match = re.search(
            r"\b(?:data\s*(?:size|volume|catalog))\s*:\s*([~\d.,]+\s*(?:TiB|TB|TБ|GiB|GB|GБ|MiB|MB))",
            card_text, re.I,
        )
        files_match = re.search(r"\b([\d][\d, ]*)\s*Files\b", card_text, re.I)
        if size_match:
            metadata.append(f"Data size: {re.sub(r'\s+', ' ', size_match.group(1)).strip()}")
        if files_match:
            metadata.append(f"File count: {re.sub(r'\s+', ' ', files_match.group(1)).strip()}")
        if progress_value is not None:
            metadata.append(f"Upload progress: {progress_value}%")

        status = "published" if progress_value == 100 else "yet_to_publish" if progress_value is not None else None
        record = {
            "organization": name,
            "country": None,
            "listed_date": None,
            "source_created_at": None,
            "source_record_id": button.get("data-company") or name.casefold(),
            "domain": domain,
            "categories": [],
            "descriptions": metadata,
            "source_publication_status": status,
        }
        _record(records, site, name, source_record_id=record["source_record_id"], domain=domain)
        if records and records[-1]["organization"].casefold() == name.casefold():
            records[-1].update(record)

    errors = [] if records else ["no Rhysida archive company records matched"]
    screenshot, dimensions = _capture_listing_screenshot(site.url, tor_host, tor_port, "#last_company")
    page = {
        "url": response.url,
        "title": "Rhysida archive",
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "text/html"),
        "records": records,
        "response_metadata": {"date_inspection": inspect_markup_dates(response.text, records)},
        "screenshot": screenshot,
    }
    if screenshot:
        page.update({"screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                     "screenshot_dimensions": dimensions})
    return {"site": site, "pages": [page] if records else [], "pages_visited": 1,
            "errors": errors, "challenge": None}


def _collect_redact_listing(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Read REDACT's company table and its visible metadata only."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    try:
        response = requests.get(
            site.url,
            proxies={"http": proxy, "https": proxy},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
            timeout=(20, 60),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"REDACT company-list request failed: {type(exc).__name__}: {str(exc)[:300]}"],
                "challenge": None}

    soup = BeautifulSoup(response.text, "html.parser")
    challenge = _source_challenge(soup.get_text(" ", strip=True))
    if challenge:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [challenge], "challenge": challenge}

    records = []
    table = soup.select_one("table")
    for row in table.select("tbody tr") if table else []:
        cells = row.select("td")
        if len(cells) < 6:
            continue
        values = [_text(cell) for cell in cells]
        name = values[0]
        if not name:
            continue
        metadata = []
        for label, value in (("Revenue", values[1]), ("Sector", values[2]),
                             ("Stock ticker", values[3]), ("Data size", values[4]),
                             ("File count", values[5])):
            if value:
                metadata.append(f"{label}: {value}")
        action = values[6].casefold() if len(values) > 6 else ""
        record = {
            "organization": name,
            "country": None,
            "listed_date": None,
            "source_created_at": None,
            "source_record_id": name.casefold(),
            "domain": None,
            "categories": [],
            "descriptions": metadata,
            "source_publication_status": "published" if action == "download" else None,
        }
        _record(records, site, name, source_record_id=name.casefold())
        if records and records[-1]["organization"].casefold() == name.casefold():
            records[-1].update(record)

    errors = [] if records else ["no REDACT company rows matched the listing table"]
    screenshot, dimensions = _capture_listing_screenshot(site.url, tor_host, tor_port, "table tbody tr")
    page = {
        "url": response.url,
        "title": soup.title.get_text(" ", strip=True) if soup.title else "REDACT companies",
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "text/html"),
        "records": records,
        "response_metadata": {"date_inspection": inspect_markup_dates(response.text, records)},
        "screenshot": screenshot,
    }
    if screenshot:
        page.update({"screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                     "screenshot_dimensions": dimensions})
    return {"site": site, "pages": [page] if records else [], "pages_visited": 1,
            "errors": errors, "challenge": None}


def _collect_safepay_listing(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Collect SafePay's public listing cards and pagination without opening victim posts."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    session = requests.Session()
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"})

    def fetch(page_number: int):
        url = site.url if page_number == 1 else f"{site.url}?{urlencode({'page': page_number})}"
        response = session.get(url, timeout=(20, 90))
        response.raise_for_status()
        return response

    try:
        first_response = fetch(1)
    except requests.RequestException as exc:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [f"SafePay listing request failed: {type(exc).__name__}: {str(exc)[:300]}"],
                "challenge": None}

    first_soup = BeautifulSoup(first_response.text, "html.parser")
    challenge = _source_challenge(first_soup.get_text(" ", strip=True))
    if challenge:
        return {"site": site, "pages": [], "pages_visited": 1,
                "errors": [challenge], "challenge": challenge}

    last_page = 1
    for link in first_soup.select("a[href]"):
        href = urljoin(first_response.url, link.get("href", ""))
        if urlparse(href).netloc.casefold() != urlparse(site.url).netloc.casefold():
            continue
        page_values = parse_qs(urlparse(href).query).get("page", [])
        for value in page_values:
            if value.isdigit():
                last_page = max(last_page, min(100, int(value)))

    pages = []
    errors = []
    pages_visited = 0
    date_selector = "time[datetime], .leak-date, .published-date"
    for page_number in range(1, last_page + 1):
        try:
            response = first_response if page_number == 1 else fetch(page_number)
        except requests.RequestException as exc:
            errors.append(f"SafePay page {page_number} request failed: {type(exc).__name__}: {str(exc)[:250]}")
            break
        pages_visited += 1
        soup = first_soup if page_number == 1 else BeautifulSoup(response.text, "html.parser")
        if page_number > 1:
            challenge = _source_challenge(soup.get_text(" ", strip=True))
            if challenge:
                errors.append(f"page {page_number}: {challenge}")
                break

        records = []
        for card in soup.select(".card"):
            title_node = card.select_one(".card-title, h5")
            name = _text(title_node) if title_node else ""
            if not name:
                continue
            hostname = name.casefold().removeprefix("www.")
            domain = hostname if re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}", hostname) else None
            status_text = _text(card.select_one(".published-text")) if card.select_one(".published-text") else ""
            status = "published" if status_text.casefold() == "published" else None
            date_node = card.select_one(date_selector)
            listed_date = (date_node.get("datetime") or _text(date_node)) if date_node else None
            size_match = re.search(r"\b(?:data\s*(?:size|volume))\s*[:：]\s*([\d.,]+\s*(?:TB|GB|MB|TiB|GiB|MiB))", _text(card), re.I)
            metadata = [f"Data size: {size_match.group(1)}"] if size_match else []
            flag = card.select_one("img[alt]")
            country = _text(flag).strip("()") if flag and re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,50}", flag.get("alt", "")) else None
            source_id = domain or re.sub(r"\W+", "-", name.casefold()).strip("-")
            record = {
                "organization": name,
                "country": country,
                "listed_date": listed_date,
                "source_created_at": None,
                "source_record_id": source_id,
                "domain": domain,
                "categories": [],
                "descriptions": metadata,
                "source_publication_status": status,
            }
            _record(records, site, name, country=country, listed_date=listed_date,
                    source_record_id=source_id, domain=domain)
            if records and records[-1]["organization"].casefold() == name.casefold():
                records[-1].update(record)

        pages.append({
            "url": response.url,
            "title": soup.title.get_text(" ", strip=True) if soup.title else "SafePay Blog",
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "text/html"),
            "records": records,
            "response_metadata": {"date_inspection": inspect_markup_dates(response.text, records)},
            "screenshot": b"",
        })
        if page_number == 1:
            screenshot, dimensions = _capture_listing_screenshot(site.url, tor_host, tor_port, ".card")
            if screenshot:
                pages[-1].update({"screenshot": screenshot,
                                  "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                                  "screenshot_dimensions": dimensions})
        if page_number < last_page:
            time.sleep(0.2)

    return {"site": site, "pages": pages, "pages_visited": pages_visited,
            "errors": errors or ([] if any(page["records"] for page in pages) else ["no SafePay victim cards found"]),
            "challenge": challenge}


def _collect_audit_team_listing(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Read Audit Team's paginated public cards, without following card links."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    session = requests.Session()
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"})
    pages = []
    errors = []
    seen_pages = set()
    queue = [site.url]
    while queue and len(seen_pages) < 20:
        url = queue.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        try:
            response = session.get(url, timeout=(45, 180))
            response.raise_for_status()
        except requests.RequestException as exc:
            errors.append(f"Audit Team listing request failed: {type(exc).__name__}: {str(exc)[:250]}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        if not pages:
            challenge = _source_challenge(soup.get_text(" ", strip=True))
            if challenge:
                return {"site": site, "pages": [], "pages_visited": 1,
                        "errors": [challenge], "challenge": challenge}

        records = []
        for card in soup.select(".card"):
            title_node = card.select_one(".title")
            status_node = card.select_one("[class*=status-]")
            if not title_node or not status_node:
                continue
            name = _text(title_node)
            if not name:
                continue
            status_class = next((value for value in status_node.get("class", []) if value.startswith("status-")), "")
            source_status = status_class.removeprefix("status-").casefold()
            publication_status = (
                "published" if source_status in {"public_transparency", "published", "leaked"}
                else "yet_to_publish" if source_status == "remediation_window"
                else None
            )
            timer = card.select_one(".mini-timer[data-deadline], [data-deadline]")
            deadline_raw = timer.get("data-deadline") if timer else None
            deadline = None
            if deadline_raw:
                if re.fullmatch(r"\d{10,13}", deadline_raw.strip()):
                    timestamp = int(deadline_raw)
                    deadline = datetime.fromtimestamp(timestamp / (1000 if timestamp > 10**11 else 1), timezone.utc)
                else:
                    deadline = _parse_datetime(deadline_raw)
            date_node = card.select_one("time[datetime], .leak-date, .published-date")
            listed_date = (date_node.get("datetime") or _text(date_node)) if date_node else None
            hostname_match = re.fullmatch(r"(?:www\.)?((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})", name, re.I)
            domain = hostname_match.group(1).casefold().removeprefix("www.") if hostname_match else None
            country_node = card.select_one("img[alt], .country, [data-country]")
            country = None
            if country_node:
                country = (country_node.get("data-country") or country_node.get("alt") or _text(country_node) or "").strip() or None
            source_id = domain or re.sub(r"\W+", "-", name.casefold()).strip("-")
            record = {
                "organization": name,
                "country": country,
                "listed_date": listed_date,
                "source_created_at": None,
                "source_record_id": source_id,
                "domain": domain,
                "categories": [],
                "descriptions": [],
                "source_publication_status": publication_status,
                "source_status": source_status,
                "estimated_publish_at": deadline.isoformat() if deadline else None,
                "countdown_raw": deadline_raw,
            }
            _record(records, site, name, country=country, listed_date=listed_date,
                    source_record_id=source_id, domain=domain)
            if records and records[-1]["organization"].casefold() == name.casefold():
                records[-1].update(record)

        pages.append({
            "url": response.url,
            "title": soup.title.get_text(" ", strip=True) if soup.title else site.name,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "text/html"),
            "records": records,
            "response_metadata": {"date_inspection": inspect_markup_dates(response.text, records)},
            "screenshot": b"",
        })
        current_page = int(parse_qs(urlparse(response.url).query).get("page", ["1"])[0])
        for link in soup.select("a[href]"):
            next_url = urljoin(response.url, link.get("href", ""))
            parsed = urlparse(next_url)
            if parsed.netloc.casefold() != urlparse(site.url).netloc.casefold():
                continue
            values = parse_qs(parsed.query).get("page", [])
            if values and values[0].isdigit() and int(values[0]) > current_page and next_url not in seen_pages:
                queue.append(next_url)
        if len(pages) == 1:
            screenshot, dimensions = _capture_listing_screenshot(site.url, tor_host, tor_port, ".card .title")
            if screenshot:
                pages[-1].update({"screenshot": screenshot,
                                  "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                                  "screenshot_dimensions": dimensions})
        time.sleep(0.15)

    session.close()
    if len(seen_pages) >= 20 and queue:
        errors.append("Audit Team pagination stopped at the 20-page safety limit")
    if not errors and not any(page["records"] for page in pages):
        errors.append("no Audit Team victim cards matched")
    return {"site": site, "pages": pages, "pages_visited": len(pages), "errors": errors, "challenge": None}


def _collect_arachna_listing(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Parse Arachna's server-rendered post list without waiting on slow page assets."""
    proxy = f"socks5h://{tor_host}:{tor_port}"
    session = requests.Session()
    session.trust_env = False
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    pages, errors, visited = [], [], set()
    queue = [site.url]
    origin = urlparse(site.url).netloc.casefold()
    challenge = None
    while queue and len(visited) < MAX_PAGES_PER_SITE:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            response = session.get(url, timeout=(45, 180), allow_redirects=True)
            if response.status_code == 304:
                response = session.get(
                    url,
                    headers={"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"},
                    timeout=(45, 180),
                    allow_redirects=True,
                )
            if response.status_code == 304:
                errors.append(f"{url}: server returned 304 without a response body")
                continue
            response.raise_for_status()
        except requests.RequestException as exc:
            errors.append(f"Arachna listing request failed: {type(exc).__name__}: {str(exc)[:350]}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        challenge = _source_challenge(soup.get_text(" ", strip=True))
        if challenge:
            errors.append(challenge)
            break
        records = []
        for card in soup.select(".container .post"):
            title_node = card.select_one("h2")
            title = _text(title_node) if title_node else ""
            note_match = re.search(r"\s*\((Leaking some patient data)\)\s*$", title, re.I)
            if note_match:
                title = title[:note_match.start()].strip()
            if not title:
                continue
            time_node = card.select_one("time[datetime], time, [data-date]")
            date_value = ""
            if time_node:
                date_value = time_node.get("datetime") or time_node.get("data-date") or _text(time_node)
            date_match = re.search(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", date_value)
            links = card.select("a[href]")
            _record(
                records,
                site,
                title,
                listed_date=date_match.group(0) if date_match else None,
                source_record_id=title.casefold(),
            )
            if not records or records[-1]["organization"].casefold() != title.casefold():
                continue
            records[-1]["source_publication_status"] = "published" if links else None
            descriptions = [
                _text(node) for node in card.select("p")
                if _text(node) and _text(node).casefold() != "files: download"
            ]
            if note_match:
                descriptions.append(note_match.group(1))
            records[-1]["descriptions"] = descriptions

        pages.append({
            "url": response.url,
            "title": soup.title.get_text(" ", strip=True) if soup.title else "Arachna Leaks",
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "text/html"),
            "records": records,
            "screenshot": b"",
            "response_metadata": {
                "collector": "server_rendered_listing",
                "date_inspection": inspect_markup_dates(response.text, records),
            },
        })

        for anchor in soup.select(".pagination a[href], nav.pagination a[href], a[rel~=next]"):
            next_url = urljoin(response.url, anchor.get("href", ""))
            parsed = urlparse(next_url)
            if parsed.netloc.casefold() == origin and next_url not in visited and next_url not in queue:
                queue.append(next_url)

    session.close()
    if not any(page.get("records") for page in pages) and not errors and not challenge:
        errors.append("no Arachna victim posts matched .container .post")
    return {"site": site, "pages": pages, "pages_visited": len(visited),
            "errors": errors, "challenge": challenge}


def _collect_clop_listing(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    """Read Clop's grouped archive menu; do not follow victim or torrent links."""
    driver = _make_driver(tor_host, tor_port, ignore_certificate_errors=True)
    driver.set_page_load_timeout(SLOW_HTML_SITE_PAGE_TIMEOUT_SECONDS)
    pages, errors = [], []
    challenge = None
    queue_wait_seconds = 0
    try:
        try:
            driver.get(site.url)
        except TimeoutException:
            # The queue can hold navigation open while it advances to the listing.
            pass

        initial_text = ""
        body_nodes = driver.find_elements("tag name", "body")
        if body_nodes:
            initial_text = _text(body_nodes[0])[:1200]
        if "access queue" in f"{driver.title} {initial_text}".casefold():
            try:
                # Clop's queue accepts a single click anywhere in the page.
                driver.find_element("tag name", "body").click()
                started = time.monotonic()
                WebDriverWait(driver, 180, poll_frequency=2).until(
                    lambda current: bool(current.find_elements(
                        "css selector", 'a.g-menu-item-container[href*="/archive/"]'
                    ))
                )
                queue_wait_seconds = round(time.monotonic() - started, 1)
            except (TimeoutException, WebDriverException) as exc:
                errors.append(f"Clop access queue did not reach the archive listing: {type(exc).__name__}")

        soup = BeautifulSoup(driver.page_source, "html.parser")
        body_text = soup.get_text(" ", strip=True)
        challenge = _source_challenge(body_text)
        if challenge:
            errors.append(challenge)
        else:
            origin = urlparse(site.url).netloc.casefold()
            archive_path = re.compile(r"^/archive(?:\d+)?/[^/]+/?$", re.I)
            archive_links: dict[str, tuple[str, str]] = {}
            archive_sections: set[str] = set()
            for anchor in soup.select("a.g-menu-item-container[href]"):
                href = urljoin(site.url, anchor.get("href", ""))
                parsed = urlparse(href)
                if parsed.netloc.casefold() != origin or not archive_path.fullmatch(parsed.path):
                    continue
                path = parsed.path.rstrip("/")
                label_node = anchor.select_one(".g-menu-item-title")
                name = _text(label_node) if label_node else _text(anchor)
                if not name:
                    continue
                archive_section = re.match(r"^(/archive\d*)/", path, re.I)
                if archive_section:
                    archive_sections.add(archive_section.group(1).casefold())
                archive_links.setdefault(path.casefold(), (name, path))

            records = []
            for _, (name, path) in sorted(archive_links.items(), key=lambda item: item[0]):
                slug = path.rsplit("/", 1)[-1]
                domain = name.casefold().removeprefix("www.").rstrip(".")
                if not re.fullmatch(
                    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
                    domain,
                ):
                    domain = None
                _record(records, site, name, source_record_id=slug, domain=domain)
                if records and records[-1]["organization"].casefold() == name.casefold():
                    # Entries under Clop's archive menus represent already listed victims.
                    records[-1]["source_publication_status"] = "published"
                    records[-1]["descriptions"] = []

            date_inspection = inspect_markup_dates(driver.page_source, records)
            screenshot, dimensions = _screenshot(driver)
            page = {
                "url": driver.current_url,
                "title": driver.title,
                "status_code": 200 if records else None,
                "content_type": "text/html",
                "records": records,
                "screenshot": screenshot,
                "response_metadata": {
                    "collector": "clop_archive_menu",
                    "archive_sections": len(archive_sections),
                    "archive_links": len(archive_links),
                    "queue_wait_seconds": queue_wait_seconds,
                    "date_inspection": date_inspection,
                },
            }
            if screenshot:
                page.update({
                    "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                    "screenshot_dimensions": dimensions,
                })
            pages.append(page)
            if not records and not errors:
                errors.append("no Clop archive entries matched the grouped archive menu")
    except WebDriverException as exc:
        errors.append(f"Clop browser collection failed: {type(exc).__name__}: {str(exc)[:350]}")
    finally:
        driver.quit()

    return {"site": site, "pages": pages, "pages_visited": len(pages),
            "errors": errors, "challenge": challenge}


def collect_site_pages(site: HtmlLeakSite, tor_host: str, tor_port: int) -> dict:
    if site.slug == "pear_ransomware":
        return _collect_pear(site, tor_host, tor_port)
    if site.slug == "sarcoma":
        return _collect_sarcoma(site, tor_host, tor_port)
    if site.slug == "run_some_wares":
        return _collect_run_some_wares(site, tor_host, tor_port)
    if site.slug == "sb_leaks":
        return _collect_sb_leaks(site, tor_host, tor_port)
    if site.slug == "ransomexx_v2":
        return _collect_ransomexx_v2(site, tor_host, tor_port)
    if site.slug == "leakeddata":
        return _collect_leakeddata(site)
    if site.slug == "fulcrum_sec":
        return _collect_fulcrum_sec(site, tor_host, tor_port)
    if site.slug == "toufan_leaks":
        return _collect_toufan_leaks(site)
    if site.slug == "clop":
        return _collect_clop_listing(site, tor_host, tor_port)
    if site.slug == "arachna":
        return _collect_arachna_listing(site, tor_host, tor_port)
    if site.slug == "blackout_ransomware":
        return _collect_blackout_listing(site, tor_host, tor_port)
    if site.slug == "beast_leaks":
        return _collect_beast_listing(site, tor_host, tor_port)
    if site.slug == "rhysida":
        return _collect_rhysida_listing(site, tor_host, tor_port)
    if site.slug == "redact":
        return _collect_redact_listing(site, tor_host, tor_port)
    if site.slug == "safepay":
        return _collect_safepay_listing(site, tor_host, tor_port)
    if site.slug == "audit_team":
        return _collect_audit_team_listing(site, tor_host, tor_port)
    if site.slug == "play_ransomware":
        return _collect_play_site_pages(site, tor_host, tor_port)
    if site.slug == "payload":
        return _collect_payload_listing(site, tor_host, tor_port)
    driver = _make_driver(
        tor_host,
        tor_port,
        page_load_timeout=(
            VERY_SLOW_HTML_SITE_PAGE_TIMEOUT_SECONDS
            if site.slug in VERY_SLOW_HTML_SITE_SLUGS
            else SLOW_HTML_SITE_PAGE_TIMEOUT_SECONDS
            if site.slug in SLOW_HTML_SITE_SLUGS
            else PAGE_TIMEOUT_SECONDS
        ),
        webdriver_command_timeout=360 if site.slug in VERY_SLOW_HTML_SITE_SLUGS else 120,
    )
    start = site.url
    origin = f"{urlparse(start).scheme}://{urlparse(start).netloc}"
    queue, visited, pages = [start], set(), []
    errors = []
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
                    page_timeout = (
                        VERY_SLOW_HTML_SITE_PAGE_TIMEOUT_SECONDS
                        if site.slug in VERY_SLOW_HTML_SITE_SLUGS
                        else SLOW_HTML_SITE_PAGE_TIMEOUT_SECONDS
                        if site.slug in SLOW_HTML_SITE_SLUGS
                        else PAGE_TIMEOUT_SECONDS
                    )
                    errors.append(f"page load exceeded {page_timeout}s: {url}")
                WebDriverWait(driver, RENDER_WAIT_SECONDS).until(
                    lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
                )
                body_class = driver.execute_script("return document.body?.className || ''")
                body_text = _text(driver.find_element("tag name", "body"))
                if "neterror" in body_class.split() or "ERR_TIMED_OUT" in body_text:
                    errors.append(f"navigation timed out through the configured Tor service: {url}")
                    continue
                if site.slug == "qilin":
                    try:
                        WebDriverWait(driver, 20).until(
                            lambda d: d.find_elements("css selector", ".item_box .item_box-title")
                        )
                    except TimeoutException:
                        errors.append("Qilin listing cards did not render within 20s")
                        continue
                if site.slug == "global_secret_group":
                    # GSG animates a full-page intro for about 6 seconds. The
                    # cards exist in the DOM before they are visible, so reading
                    # element.text immediately can silently produce zero victims.
                    WebDriverWait(driver, 12).until(
                        lambda d: not d.execute_script(
                            "return document.documentElement.classList.contains('gsg-loader-active')"
                        )
                    )
                time.sleep(1.5)
                challenge = _challenge(driver, site.slug)
                if challenge:
                    errors.append(challenge)
                    break
                rows = _extract(driver, site)
                date_inspection = inspect_markup_dates(driver.page_source, rows)
                if site.slug == "vexy":
                    # Vexy's company cards render the listing date as visible
                    # text in `.date-row`; its name-only scraper missed it.
                    # Use this source-specific, one-date-per-card pattern only.
                    recovered = 0
                    for record in rows:
                        if record.get("listed_date"):
                            continue
                        candidates = [
                            item for item in record.get("markup_date_candidates", [])
                            if item.get("class_name") == "date-row" and not item.get("hidden")
                        ]
                        dates = {item.get("normalized_date") for item in candidates if item.get("normalized_date")}
                        if len(dates) == 1:
                            record["listed_date"] = dates.pop()
                            recovered += 1
                    date_inspection["dates_recovered_from_markup"] = recovered
                if site.slug == "global_secret_group" and not rows:
                    errors.append(
                        "Global Secret Group returned no visible victim titles after its intro loader finished"
                    )
                    continue
                next_links = _pagination_links(driver, origin)
                screenshot, dimensions = _screenshot(driver)
                pages.append({
                    "url": driver.current_url,
                    "title": driver.title,
                    "status_code": 200,
                    "content_type": "text/html",
                    "records": rows,
                    "response_metadata": {"date_inspection": date_inspection},
                    "screenshot": screenshot,
                    "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                    "screenshot_dimensions": dimensions,
                })
                for next_url in next_links:
                    # Qilin exposes both `/` and `/?page=1` for the same first
                    # listing. The root URL is already collected above.
                    if site.slug == "qilin" and parse_qs(urlparse(next_url).query).get("page") == ["1"]:
                        continue
                    if next_url not in visited and next_url not in queue and len(visited) + len(queue) < MAX_PAGES_PER_SITE:
                        queue.append(next_url)
            except WebDriverException as exc:
                errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:350]}")
                break
    finally:
        driver.quit()
    if not any(page.get("records") for page in pages) and not challenge and not errors:
        errors.append("no victim records matched the rendered listing")
    return {"site": site, "pages": pages, "pages_visited": len(visited), "errors": errors, "challenge": challenge}
