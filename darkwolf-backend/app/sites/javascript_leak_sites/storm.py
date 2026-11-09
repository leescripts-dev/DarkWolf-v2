"""Storm test-site collector: solve in-session, then read its public JSON API."""

from __future__ import annotations

import hashlib
import importlib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium import webdriver

from app.sites.javascript_leak_sites.registry import JavascriptLeakSite


def _storm_solver():
    project_root = Path(__file__).resolve().parents[4]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    return importlib.import_module("Storm.storm_solver")


def _make_storm_driver(solver, tor_host: str, tor_port: int):
    options = webdriver.FirefoxOptions()
    options.binary_location = solver.TOR_BROWSER_BINARY
    options.add_argument("-headless")
    options.set_preference("network.proxy.type", 1)
    options.set_preference("network.proxy.socks", tor_host)
    options.set_preference("network.proxy.socks_port", tor_port)
    options.set_preference("network.proxy.socks_remote_dns", True)
    options.set_preference("network.proxy.socks_version", 5)
    return webdriver.Firefox(
        service=Service(solver.GECKODRIVER_PATH),
        options=options,
    )


def _as_datetime(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _api_records(rows: list[dict], captured_at: datetime) -> list[dict]:
    records = []
    for row in rows:
        name = " ".join(str(row.get("name") or "").split())
        if not name:
            continue
        deadline_raw = row.get("limitDay")
        deadline = _as_datetime(deadline_raw)
        created_at = row.get("createdAt")
        updated_at = row.get("updatedAt")
        source_status = str(row.get("status") or "").casefold()
        if deadline:
            publication_status = "published" if deadline <= captured_at else "yet_to_publish"
        elif source_status in {"published", "leaked", "exposed"}:
            publication_status = "published"
        elif source_status in {"warning", "pending", "awaiting"}:
            publication_status = "yet_to_publish"
        else:
            publication_status = None

        description = " ".join(str(row.get("description") or "").split())
        location = ", ".join(
            str(row.get(key)).strip()
            for key in ("city", "state")
            if row.get(key)
        )
        details = [description] if description else []
        if location:
            details.append(f"Location: {location}")
        if row.get("paidDate"):
            details.append(f"Source payment date: {row['paidDate']}")

        remaining = max(0, int((deadline - captured_at).total_seconds())) if deadline and deadline > captured_at else None
        industry = str(row.get("industry") or "").strip()
        records.append({
            "source_record_id": str(row.get("_id") or row.get("id") or name.casefold()),
            "organization": name,
            "country": str(row.get("country") or "").strip() or None,
            "listed_date": created_at,
            "source_created_at": created_at,
            "source_updated_at": updated_at,
            "domain": None,
            "categories": [industry] if industry else [],
            "descriptions": details,
            "visits": row.get("viewCount"),
            "source_publication_status": publication_status,
            "estimated_publish_at": deadline.isoformat() if deadline else None,
            "countdown_captured_at": captured_at.isoformat() if remaining is not None else None,
            "countdown_seconds_at_capture": remaining,
            "countdown_raw": deadline_raw,
            "preserve_countdown_when_published": bool(deadline),
        })
    return records


def collect_storm(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    """Use the same headless Firefox session for challenge completion and API read.

    Session cookies remain in Firefox's temporary profile; this collector never
    reads, prints, or persists them.
    """
    solver = _storm_solver()
    driver = None
    errors: list[str] = []
    challenge = None
    pages: list[dict] = []
    try:
        driver = _make_storm_driver(solver, tor_host, tor_port)
        driver.set_page_load_timeout(180)
        driver.set_script_timeout(120)
        driver.get(site.url)
        WebDriverWait(driver, 120).until(
            lambda browser: browser.execute_script("return document.readyState")
            in ("interactive", "complete")
        )
        time.sleep(5)

        if urlparse(driver.current_url).netloc.lower() != urlparse(site.url).netloc.lower():
            errors.append(f"navigation left the configured Storm origin: {driver.current_url}")
            return {"site": site, "pages": [], "pages_visited": 1, "errors": errors, "challenge": None}

        if driver.find_elements(By.CSS_SELECTOR, "[data-bolt='true']"):
            if not solver.solve_storm_captcha(driver, timeout=60):
                challenge = "Storm challenge solver did not reach its success state"
                errors.append(challenge)
                return {"site": site, "pages": [], "pages_visited": 1, "errors": errors, "challenge": challenge}
            WebDriverWait(driver, 30).until(
                lambda browser: not browser.find_elements(By.CSS_SELECTOR, "[data-bolt='true']")
            )

        if not site.api_url:
            errors.append("Storm API URL is missing from the site registry")
            return {"site": site, "pages": [], "pages_visited": 1, "errors": errors, "challenge": None}

        # Fetch inside the verified browser context; do not export its cookie.
        response = driver.execute_async_script("""
            const done = arguments[arguments.length - 1];
            fetch(arguments[0], {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
              .then(async response => {
                let payload;
                try { payload = await response.json(); }
                catch (_) { payload = {error: 'API response was not JSON'}; }
                if (!response.ok) {
                  done({status: response.status, error: payload.error || `HTTP ${response.status}`});
                  return;
                }
                const rows = Array.isArray(payload) ? payload : (payload.items || payload.companies || []);
                done({status: response.status, rows: rows.map(row => ({
                  _id: row._id || row.id,
                  name: row.name || row.companyName,
                  country: row.country,
                  state: row.state,
                  city: row.city,
                  industry: row.industry,
                  description: row.description,
                  limitDay: row.limitDay,
                  status: row.status,
                  paidDate: row.paidDate,
                  viewCount: row.viewCount,
                  createdAt: row.createdAt,
                  updatedAt: row.updatedAt,
                  visible: row.visible
                }))});
              }).catch(error => done({error: String(error)}));
        """, site.api_url)

        if response.get("error") or response.get("status") != 200:
            message = response.get("error") or f"Storm API returned HTTP {response.get('status')}"
            if "captcha session required" in str(message).casefold():
                challenge = "Storm API still requires a cleared captcha session"
            errors.append(str(message))
            return {"site": site, "pages": [], "pages_visited": 1, "errors": errors, "challenge": challenge}

        captured_at = datetime.now(timezone.utc)
        records = _api_records(response.get("rows") or [], captured_at)
        if not records:
            errors.append("Storm API returned no usable victim records")
            return {"site": site, "pages": [], "pages_visited": 1, "errors": errors, "challenge": None}

        screenshot, dimensions = driver.get_screenshot_as_png(), {
            "width": int(driver.execute_script("return window.innerWidth")),
            "height": int(driver.execute_script("return window.innerHeight")),
            "full_page": False,
        }
        pages.append({
            "url": site.api_url,
            "title": driver.title or site.name,
            "status_code": 200,
            "content_type": "application/json",
            "records": records,
            "response_metadata": {
                "collector": "storm_verified_session_json_api",
                "total_records": len(records),
                "pagination": "The companies endpoint returned the complete listing in one response.",
                "captured_at": captured_at.isoformat(),
            },
            "screenshot": screenshot,
            "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
            "screenshot_dimensions": dimensions,
        })
    except TimeoutException as exc:
        errors.append(f"Storm page/API timed out: {type(exc).__name__}: {str(exc)[:300]}")
    except (WebDriverException, ImportError, OSError, ValueError) as exc:
        errors.append(f"Storm collector failed: {type(exc).__name__}: {str(exc)[:300]}")
    finally:
        if driver:
            try:
                driver.quit()
            except WebDriverException:
                pass
    return {
        "site": site,
        "pages": pages,
        "pages_visited": 1,
        "errors": errors,
        "challenge": challenge,
    }
