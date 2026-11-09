"""Collector for the Insomnia test site's math-gated HTML listing."""

from __future__ import annotations

import hashlib
import importlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from app.sites.html_leak_sites.collector import _make_driver, _screenshot
from app.sites.javascript_leak_sites.registry import JavascriptLeakSite
from app.sites.markup_date_inspector import inspect_markup_dates


def _load_insomnia_solver():
    project_root = Path(__file__).resolve().parents[4]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    return importlib.import_module("Insomnia.captcha_solver")


def _field(card: BeautifulSoup, label: str) -> str | None:
    for item in card.select(".card-meta span"):
        strong = item.find("strong")
        if not strong or strong.get_text(" ", strip=True).rstrip(":").casefold() != label.casefold():
            continue
        text = item.get_text(" ", strip=True)
        return re.sub(rf"^{re.escape(label)}\s*:\s*", "", text, flags=re.I).strip() or None
    return None


def _country(location: str | None) -> str | None:
    if not location:
        return None
    country = re.sub(r"\s+", " ", location.split(",")[-1]).strip()
    aliases = {
        "usa": "United States", "u.s.a.": "United States", "us": "United States",
        "uk": "United Kingdom", "u.k.": "United Kingdom",
    }
    return aliases.get(country.casefold(), country) or None


def _extract_records(html_source: str) -> list[dict]:
    soup = BeautifulSoup(html_source or "", "html.parser")
    records, seen = [], set()
    for card in soup.select(".book-card"):
        title = card.select_one(".info-title a")
        organization = re.sub(r"\s+", " ", title.get_text(" ", strip=True) if title else "").strip()
        if not organization or organization.casefold() in seen:
            continue
        seen.add(organization.casefold())

        website = _field(card, "Website")
        domain = None
        if website:
            parsed = urlparse(website if "://" in website else f"https://{website}")
            host = parsed.hostname
            if host and "." in host:
                domain = host.casefold().removeprefix("www.")

        notified = _field(card, "Notified")
        description_node = card.select_one(".info-desc")
        description = re.sub(r"\s+", " ", description_node.get_text(" ", strip=True)) if description_node else ""
        author_node = card.select_one(".info-author")
        category = re.sub(r"\s+", " ", author_node.get_text(" ", strip=True)) if author_node else ""
        extra = [description] if description else []
        revenue, employees = _field(card, "Revenue"), _field(card, "Employees")
        if revenue:
            extra.append(f"Revenue: {revenue}")
        if employees:
            extra.append(f"Employees: {employees}")

        href = title.get("href", "") if title else ""
        slug = urlparse(href).path.strip("/").split("/")[-1] if href else ""
        records.append({
            "source_record_id": slug or organization.casefold(),
            "organization": organization,
            "country": _country(_field(card, "Location")),
            "listed_date": notified,
            "source_created_at": notified,
            "website": f"https://{domain}" if domain else None,
            "domain": domain,
            "categories": [category] if category else [],
            "descriptions": extra,
            "source_publication_status": "published",
        })
    return records


def collect_insomnia(site: JavascriptLeakSite, tor_host: str, tor_port: int) -> dict:
    driver = None
    pages, errors = [], []
    challenge = None
    try:
        driver = _make_driver(tor_host, tor_port, page_load_timeout=90)
        driver.get(site.url)
        WebDriverWait(driver, 45).until(
            lambda browser: browser.execute_script("return document.readyState") in ("interactive", "complete")
        )

        if driver.find_elements(By.CSS_SELECTOR, "#captcha-question"):
            solver = _load_insomnia_solver()
            question = WebDriverWait(driver, 20).until(
                lambda browser: browser.find_element(By.CSS_SELECTOR, "#captcha-question").text.strip()
            )
            answer = solver.solve_math_captcha(question)
            if answer is None:
                challenge = "Insomnia math challenge could not be parsed"
                return {"site": site, "pages": [], "pages_visited": 1,
                        "errors": [challenge], "challenge": challenge}
            input_box = driver.find_element(By.CSS_SELECTOR, "#captcha-input")
            input_box.clear()
            input_box.send_keys(str(answer))
            driver.find_element(By.CSS_SELECTOR, "#captcha-button").click()
            WebDriverWait(driver, 15).until(
                lambda browser: browser.execute_script(
                    "return getComputedStyle(document.querySelector('#main-content')).display !== 'none'"
                )
            )

        html_source = driver.page_source
        records = _extract_records(html_source)
        if not records:
            errors.append("no Insomnia .book-card victim records found after verification")
        else:
            captured_at = datetime.now(timezone.utc)
            screenshot, dimensions = _screenshot(driver)
            pages.append({
                "url": driver.current_url,
                "title": driver.title,
                "status_code": 200,
                "content_type": "text/html",
                "records": records,
                "response_metadata": {
                    "collector": "insomnia_verified_html_cards",
                    "pagination": "No pagination controls were present in the inspected listing markup",
                    "date_inspection": inspect_markup_dates(html_source, records),
                },
                "screenshot": screenshot,
                "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
                "screenshot_dimensions": dimensions,
            })
    except (TimeoutException, WebDriverException, ImportError, ValueError) as exc:
        errors.append(f"{type(exc).__name__}: {str(exc)[:350]}")
    finally:
        if driver:
            try:
                driver.quit()
            except WebDriverException:
                pass
    return {"site": site, "pages": pages, "pages_visited": 1, "errors": errors, "challenge": challenge}
