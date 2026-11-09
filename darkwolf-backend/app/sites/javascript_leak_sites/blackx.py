"""BlackX's client-rendered public listing collector."""

from __future__ import annotations

import importlib
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup

from app.sites.html_leak_sites.collector import _make_driver, _screenshot
from app.sites.markup_date_inspector import inspect_markup_dates
from app.sites.javascript_leak_sites.registry import JavascriptLeakSite


def _load_captcha_solver():
    backend_root = Path(__file__).resolve().parents[3]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    return importlib.import_module("Captchy.captcha_solver")


def _date_value(value) -> datetime | None:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 100_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _publish_deadline(reg_time, period) -> datetime | None:
    base = _date_value(reg_time)
    if not base or not isinstance(period, dict):
        return None
    try:
        months = int(period.get("months") or 0)
        days = int(period.get("days") or 0)
        hours = int(period.get("hours") or 0)
    except (TypeError, ValueError):
        return None
    month_index = base.month - 1 + months
    year, month = base.year + month_index // 12, month_index % 12 + 1
    import calendar
    try:
        day = min(base.day, calendar.monthrange(year, month)[1])
        return base.replace(year=year, month=month, day=day) + timedelta(days=days, hours=hours)
    except (OverflowError, ValueError):
        return None


def _text_values(record: dict, keys: tuple[str, ...]) -> list[str]:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True) if "<" in value and ">" in value else value
            text = html.unescape(text).replace("\ufffd", "").strip()
            return [re.sub(r"\s+", " ", text)] if text else []
        if isinstance(value, list):
            values = []
            for item in value:
                raw = str(item).strip()
                if not raw:
                    continue
                text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True) if "<" in raw and ">" in raw else raw
                text = html.unescape(text).replace("\ufffd", "").strip()
                if text:
                    values.append(re.sub(r"\s+", " ", text))
            if values:
                return values
    return []


def _parse_target(row: dict, captured_at: datetime) -> dict | None:
    name = re.sub(r"\s+", " ", str(row.get("name") or "")).strip()
    if not name:
        return None

    raw_url = str(row.get("url") or "").strip()
    domain = None
    clear_domain = False
    if raw_url:
        candidate = raw_url if "://" in raw_url else f"https://{raw_url}"
        host = urlparse(candidate).hostname
        if host and "." in host:
            domain = host.casefold().removeprefix("www.")
            if domain in {
                "wa.me", "whatsapp.com", "t.me", "telegram.org", "discord.gg",
                "discord.com", "x.com", "twitter.com", "facebook.com",
                "linkedin.com", "instagram.com",
            }:
                domain = None
                clear_domain = True

    listed_at = _date_value(row.get("regTime"))
    deadline = _publish_deadline(row.get("regTime"), row.get("period"))
    explicit_status = str(row.get("status") or row.get("state") or row.get("publicationStatus") or "").casefold()
    if deadline:
        publication_status = "published" if captured_at >= deadline else "yet_to_publish"
    elif any(word in explicit_status for word in ("publish", "leak", "expos")):
        publication_status = "published"
    else:
        publication_status = None

    descriptions = _text_values(row, ("description", "desc", "summary", "note", "details"))
    size = next((row.get(key) for key in ("dataSize", "leakSize", "size") if row.get(key) not in (None, "")), None)
    if size is not None:
        descriptions.insert(0, f"Data size: {size}")

    categories = row.get("categories") or row.get("tags") or []
    if not isinstance(categories, list):
        categories = [str(categories)]

    countdown = max(0, int((deadline - captured_at).total_seconds())) if deadline and deadline > captured_at else None
    return {
        "source_record_id": str(row.get("_id") or row.get("id") or domain or name.casefold()),
        "organization": name,
        "country": row.get("country") or None,
        "listed_date": listed_at.isoformat() if listed_at else None,
        "source_created_at": listed_at.isoformat() if listed_at else None,
        "source_updated_at": row.get("updatedAt") or row.get("updated_at"),
        "website": raw_url or None,
        "domain": domain,
        "clear_domain": clear_domain,
        "categories": categories,
        "descriptions": descriptions,
        "size": str(size) if size is not None else None,
        "leak_size": str(size) if size is not None else None,
        "source_publication_status": publication_status,
        "estimated_publish_at": deadline.isoformat() if deadline else None,
        "countdown_captured_at": captured_at.isoformat() if deadline and deadline > captured_at else None,
        "countdown_seconds_at_capture": countdown,
        "countdown_raw": json.dumps(row.get("period"), ensure_ascii=False) if isinstance(row.get("period"), dict) else None,
    }


def collect_blackx(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    """Verify in the source UI, then read its public `/api/targets` listing."""
    driver = None
    pages, errors = [], []
    challenge = None
    try:
        driver = _make_driver(tor_host, tor_port, page_load_timeout=90)
        driver.get(site.url)
        WebDriverWait(driver, 45).until(
            lambda browser: browser.execute_script("return document.readyState") in ("interactive", "complete")
        )
        WebDriverWait(driver, 30).until(
            lambda browser: bool(browser.find_elements("css selector", ".captcha__svg svg, .target-card, .leaked-page__heading"))
        )

        if driver.find_elements("css selector", ".captcha__svg svg"):
            try:
                solver = _load_captcha_solver()
                model_path = Path(__file__).resolve().parents[3] / "Captchy" / "captcha_model.pt"
                solved, reason = solver.solve_with_driver(driver, model_path=str(model_path))
            except (ImportError, OSError, RuntimeError) as exc:
                solved, reason = False, f"captcha model unavailable: {type(exc).__name__}: {str(exc)[:180]}"
            if not solved:
                challenge = "BlackX verification was not completed"
                errors.append(reason or challenge)
                return {"site": site, "pages": pages, "pages_visited": 1, "errors": errors, "challenge": challenge}

        # The application itself uses this same same-origin public listing call.
        response = driver.execute_async_script("""
          const done = arguments[0];
          fetch('/api/targets', {credentials: 'same-origin', headers: {Accept: 'application/json'}})
            .then(async response => done({status: response.status, body: await response.text()}))
            .catch(error => done({error: String(error)}));
        """)
        if not isinstance(response, dict) or response.get("error"):
            raise ValueError(f"BlackX listing request failed: {response.get('error') if isinstance(response, dict) else 'invalid browser response'}")
        if int(response.get("status") or 0) != 200:
            raise ValueError(f"BlackX /api/targets returned HTTP {response.get('status')}")
        payload = json.loads(response.get("body") or "{}")
        rows = payload.get("targets") if isinstance(payload, dict) and payload.get("ok") else None
        if not isinstance(rows, list):
            raise ValueError("BlackX /api/targets response did not contain a targets array")

        captured_at = datetime.now(timezone.utc)
        records = [parsed for row in rows if isinstance(row, dict) if (parsed := _parse_target(row, captured_at))]
        if not records:
            errors.append("BlackX /api/targets returned no parseable victim records")
        else:
            screenshot, dimensions = _screenshot(driver)
            markup_dates = inspect_markup_dates(driver.page_source, records)
            pages.append({
                "url": urljoin(site.url, "/api/targets"),
                "title": driver.title or "BlackX targets",
                "status_code": int(response["status"]),
                "content_type": "application/json",
                "records": records,
                "response_metadata": {"collector": "blackx_session_api", "date_inspection": markup_dates},
                "screenshot": screenshot,
                "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                "screenshot_dimensions": dimensions,
            })
    except (TimeoutException, WebDriverException, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"{type(exc).__name__}: {str(exc)[:350]}")
    finally:
        if driver:
            try:
                driver.quit()
            except WebDriverException:
                pass
    return {"site": site, "pages": pages, "pages_visited": 1, "errors": errors, "challenge": challenge}
