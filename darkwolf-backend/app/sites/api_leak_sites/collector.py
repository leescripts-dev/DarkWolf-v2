from math import ceil
import html
import json
import re
import warnings
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests
from urllib3.exceptions import InsecureRequestWarning

from app.sites.api_leak_sites.registry import ApiLeakSite


PAGE_TIMEOUT = (20, 60)
SLOW_API_SITE_TIMEOUT = (45, 120)
SLOW_API_SITE_SLUGS = {"byod", "lapsus"}
MAX_PAGES = 100


def _page_timeout_for_site(site: ApiLeakSite) -> tuple[int, int]:
    return SLOW_API_SITE_TIMEOUT if site.slug in SLOW_API_SITE_SLUGS else PAGE_TIMEOUT


def _session_get(session: requests.Session, url: str, *, verify_tls: bool, **kwargs):
    if verify_tls:
        return session.get(url, verify=True, **kwargs)
    # Akira's onion HTTPS certificate is known to be untrusted. Keep the
    # exception scoped to this site's requests and don't emit one warning per
    # page during a full pagination run.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureRequestWarning)
        return session.get(url, verify=False, **kwargs)


def _nested(value, path: tuple[str, ...] | None):
    if path is None:
        return None
    current = value
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _normalized_record(site: ApiLeakSite, item: dict) -> dict | None:
    field_map = site.field_map or {}

    if site.slug == "byod" and str(item.get("type") or "").casefold() != "download":
        # PSA/warning cards do not represent victim entries.
        return None

    def field(name: str, default_path: tuple[str, ...]):
        return _nested(item, field_map.get(name, default_path))

    name = field("name", ("name",))
    if not isinstance(name, str) or not name.strip():
        return None
    if site.slug == "ransomhouse":
        # `/a` includes a non-victim HOT NEWS banner before the company list.
        # Only ingest public company entries; never copy their `info` payload.
        if str(item.get("private") or "").casefold() != "false":
            return None
        name = re.sub(r"^\[(?:DISCLOSED|EVIDENCE)\]\s*", "", name, flags=re.I).strip()

    chaos_domain = None
    if site.slug == "chaos_ransomware":
        # The endpoint mixes genuine domain-named posts with randomized filler.
        # Keep entries whose title is a hostname and whose public listing link
        # points to the site's ZoomInfo company profile pattern.
        if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", name.strip(), re.I):
            return None
        source_url = item.get("url")
        if not isinstance(source_url, str):
            return None
        parsed_source_url = urlsplit(source_url if "://" in source_url else f"https://{source_url}")
        source_host = (parsed_source_url.hostname or "").casefold()
        if source_host != "zoominfo.com" and not source_host.endswith(".zoominfo.com"):
            return None
        if not parsed_source_url.path.startswith("/c/"):
            return None
        chaos_domain = name.strip().casefold().removeprefix("www.")

    industry_name = field("industry", ("industry", "name"))
    if industry_name is None:
        industry_name = field("industry", ("industry",))
    website = field("website", ("companyUrl",))
    description = field("description", ("description",))
    if site.slug == "booba_project" and not website and isinstance(description, str):
        website_match = re.search(r"\bWebsite\s*:\s*(?:https?://)?([^\s/]+)", description, re.I)
        if website_match:
            website = website_match.group(1)
    hostname = None
    if isinstance(website, str) and website.strip():
        value = website.strip()
        parsed = urlsplit(value if "://" in value else f"//{value}")
        hostname = parsed.hostname
        if hostname:
            hostname = hostname.casefold().removeprefix("www.")

    entry_date = field("date", ("entryDate",))
    if chaos_domain:
        website = f"https://{chaos_domain}"
        hostname = chaos_domain
    record = {
        "source_record_id": str(field("id", ("id",)) or name.strip().casefold()),
        "organization": " ".join(name.split()),
        "country": field("country", ("countryCode",)) or field("country", ("country",)),
        "listed_date": entry_date if isinstance(entry_date, str) else None,
        "website": website.strip() if isinstance(website, str) and website.strip() else None,
        "domain": hostname,
        "categories": [industry_name.strip()] if isinstance(industry_name, str) and industry_name.strip() else [],
        "descriptions": [description.strip()] if isinstance(description, str) and description.strip() else [],
        # These public listing metadata fields are kept in raw evidence, not
        # interpreted as revenue or fetched as downloadable victim data.
        "file_count": field("file_count", ("fileCount",)),
        "storage_gb": field("storage_gb", ("storageGB",)),
    }
    if site.slug == "ransomhouse":
        raw_published = str(item.get("published") or "").strip()
        published_date = None
        if raw_published and raw_published.casefold() != "not yet":
            try:
                published_date = datetime.strptime(raw_published, "%d/%m/%Y").date().isoformat()
            except ValueError:
                try:
                    published_date = datetime.strptime(raw_published, "%Y-%m-%d").date().isoformat()
                except ValueError:
                    published_date = None
        record.update({
            "listed_date": published_date,
            "source_publication_status": "published" if published_date else "yet_to_publish",
            "source_status": str(item.get("status") or "").strip() or None,
        })
        # The source exposes victim-facing details in `info`; keep only the
        # organization and public listing metadata in normalized evidence.
        record["descriptions"] = []
    elif site.slug == "scarlett_group":
        record["descriptions"] = []
        breach = item.get("breach") if isinstance(item.get("breach"), dict) else {}
        raw_status = str(breach.get("status") or "").casefold()
        uploaded = breach.get("uploaded")
        if uploaded is not None:
            record["listed_date"] = uploaded if isinstance(uploaded, str) else None
        record["source_publication_status"] = (
            "published" if raw_status == "leaked"
            else "yet_to_publish" if raw_status == "negotiation"
            else None
        )
        deadline_raw = breach.get("deadline")
        deadline = None
        if isinstance(deadline_raw, str):
            deadline = deadline_raw
        elif isinstance(deadline_raw, (int, float)) and not isinstance(deadline_raw, bool) and deadline_raw > 0:
            deadline_seconds = deadline_raw / 1000 if deadline_raw > 10**11 else deadline_raw
            deadline = datetime.fromtimestamp(deadline_seconds, timezone.utc).isoformat()
        record["estimated_publish_at"] = deadline
        record["countdown_raw"] = str(deadline_raw) if deadline_raw is not None else None
        record["source_status"] = raw_status or None
        record["source_updated_at"] = item.get("updatedAt")
    elif site.slug == "byod":
        # BYOD repeats the `direct-download` id. Identify entries by title and
        # keep metadata only; mirror URLs are never requested or persisted.
        raw_updated = item.get("updated_on")
        date_match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", str(raw_updated or ""))
        record["source_record_id"] = f"download:{name.strip().casefold()}"
        record["listed_date"] = date_match.group(0) if date_match else None
        record["source_updated_at"] = raw_updated
        record["source_card_type"] = "download"
        size_match = re.search(r"\bSIZE\s*:\s*([^|]+)", str(raw_updated or ""), re.I)
        if size_match:
            record["descriptions"].append(f"Data size: {size_match.group(1).strip()}")
        record["source_publication_status"] = "published"
    elif site.slug == "securotrop":
        expiry = item.get("timer_expiry")
        added = item.get("time_added")
        if isinstance(added, (int, float)) and not isinstance(added, bool) and added > 0:
            added_seconds = added / 1000 if added > 10**11 else added
            record["listed_date"] = datetime.fromtimestamp(added_seconds, timezone.utc).isoformat()
        if isinstance(expiry, (int, float)) and not isinstance(expiry, bool) and expiry > 0:
            expiry_seconds = expiry / 1000 if expiry > 10**11 else expiry
            deadline = datetime.fromtimestamp(expiry_seconds, timezone.utc)
            remaining = max(0, int((deadline - datetime.now(timezone.utc)).total_seconds()))
            record.update({
                "estimated_publish_at": deadline.isoformat(),
                "countdown_captured_at": datetime.now(timezone.utc).isoformat(),
                "countdown_seconds_at_capture": remaining,
                "countdown_raw": str(expiry),
            })
        record["source_publication_status"] = "published" if item.get("is_published") is True else "yet_to_publish"
        metadata = []
        for label, key in (("Revenue", "revenue"), ("Employees", "employees"),
                            ("File count", "files"), ("Data size", "size")):
            value = item.get(key)
            if value not in (None, ""):
                if site.slug == "securotrop" and key == "size":
                    value = f"{value} GB"
                elif site.slug == "securotrop" and key == "revenue":
                    value = f"${value}M"
                metadata.append(f"{label}: {value}")
        record["descriptions"] = metadata
    elif site.slug == "vypr":
        raw_status = str(item.get("status") or "").casefold()
        record["source_publication_status"] = (
            "published" if raw_status == "published"
            else "yet_to_publish" if raw_status in {"pending", "awaiting", "unpublished"}
            else None
        )
    elif site.slug == "wallstreet":
        # Do not ingest description/content/confidential victim payload fields.
        record["descriptions"] = []
        created_at = item.get("createdAt")
        if isinstance(created_at, (int, float)) and not isinstance(created_at, bool) and created_at > 0:
            created_seconds = created_at / 1000 if created_at > 10**11 else created_at
            record["listed_date"] = datetime.fromtimestamp(created_seconds, timezone.utc).isoformat()
        ends_at = item.get("endsAt")
        deadline = None
        if isinstance(ends_at, (int, float)) and not isinstance(ends_at, bool) and ends_at > 0:
            ends_seconds = ends_at / 1000 if ends_at > 10**11 else ends_at
            deadline = datetime.fromtimestamp(ends_seconds, timezone.utc)
        paused_at = item.get("pausedAt")
        record["source_publication_status"] = (
            "published" if deadline is None or deadline <= datetime.now(timezone.utc) or paused_at
            else "yet_to_publish"
        )
        record["estimated_publish_at"] = deadline.isoformat() if deadline and record["source_publication_status"] == "yet_to_publish" else None
        record["countdown_raw"] = str(ends_at) if record["source_publication_status"] == "yet_to_publish" and ends_at is not None else None
        data_size = item.get("dataSize")
        if isinstance(data_size, str) and data_size.strip():
            record["descriptions"] = [f"Data size: {data_size.strip()}"]
        categories = item.get("categories")
        if isinstance(categories, list):
            record["categories"] = [str(value).strip() for value in categories if isinstance(value, str) and value.strip()]
    elif site.slug == "gunra":
        record["source_publication_status"] = (
            "published" if item.get("dataAccessible") is True
            else "yet_to_publish" if item.get("dataAccessible") is False
            else None
        )
        size = item.get("leakDataSizeGb")
        if isinstance(size, (int, float)) and size > 0:
            record["descriptions"] = [f"Data size: {size:g} GB"]
    elif site.slug == "lapsus":
        status = str(item.get("status") or "").casefold()
        label = str(item.get("statusLabel") or "").casefold()
        record["source_publication_status"] = (
            "published" if status in {"leaked", "published"} or "published" in label
            else "yet_to_publish" if status in {"pending", "awaiting", "unpublished"}
            else None
        )
        # Do not persist target descriptions or archive/download URLs.
        record["descriptions"] = []
    elif site.slug == "lamashtu":
        location = str(item.get("location") or "").strip().rstrip(".,; ")
        from app.api.dashboard import COUNTRY_CODES, COUNTRY_NAMES, canonical_country

        country = None
        location_parts = [part.strip(" \t\r\n.,;:()[]") for part in re.split(r"[,;]", location)]
        for part in reversed(location_parts):
            canonical = canonical_country(part)
            if canonical:
                country = canonical[1]
                break
        if country is None:
            for alias in sorted(COUNTRY_CODES, key=len, reverse=True):
                if re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", location, re.I):
                    code = COUNTRY_CODES[alias]
                    country = COUNTRY_NAMES.get(code, alias.title())
                    break
        if country is None and re.search(r"\bitalien\b", location, re.I):
            country = "Italy"
        record["country"] = country or None
        record["clear_country"] = country is None
        record["source_created_at"] = item.get("created_at")
        size = item.get("size")
        if isinstance(size, str) and size.strip():
            record["descriptions"].insert(0, f"Leak size: {size.strip()}")
        raw_publish_at = item.get("publish_at")
        deadline = None
        if isinstance(raw_publish_at, str) and raw_publish_at.strip():
            try:
                deadline = datetime.fromisoformat(raw_publish_at.strip().replace("Z", "+00:00"))
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                deadline = deadline.astimezone(timezone.utc)
            except ValueError:
                deadline = None
        captured_at = datetime.now(timezone.utc)
        remaining = max(0, int((deadline - captured_at).total_seconds())) if deadline else None
        record.update({
            "source_publication_status": "yet_to_publish" if deadline and remaining > 0 else "published",
            "estimated_publish_at": deadline.isoformat() if deadline and remaining > 0 else None,
            "countdown_captured_at": captured_at.isoformat() if deadline and remaining > 0 else None,
            "countdown_seconds_at_capture": remaining if deadline and remaining > 0 else None,
            "countdown_raw": raw_publish_at if deadline and remaining > 0 else None,
            "visits": item.get("views") if isinstance(item.get("views"), int) else None,
        })
    if site.slug == "dragonforce":
        timer = item.get("timer_publication")
        timer_stopped = item.get("is_timer_publication_stopped")
        timer_remaining = None
        if isinstance(timer, str):
            timer_remaining = int((datetime.fromisoformat(timer.replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds())
        record.update({
            "estimated_publish_at": timer if isinstance(timer, str) else None,
            "countdown_captured_at": datetime.now(timezone.utc).isoformat() if timer else None,
            "countdown_seconds_at_capture": max(0, timer_remaining) if timer_remaining is not None else None,
            "countdown_raw": timer,
            "source_publication_status": (
                "published" if timer_stopped is True else "yet_to_publish" if timer_remaining is not None and timer_remaining > 0 else None
            ),
            "file_size_bytes": item.get("weight"),
            "source_tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
        })
    elif site.slug == "d1r":
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        expires = item.get("expires_at")
        deadline = None
        if isinstance(expires, str) and expires.strip():
            try:
                deadline = datetime.fromisoformat(expires.strip().replace("Z", "+00:00"))
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                deadline = deadline.astimezone(timezone.utc)
            except ValueError:
                deadline = None
        elif isinstance(expires, (int, float)) and not isinstance(expires, bool):
            deadline = datetime.fromtimestamp(expires, timezone.utc)
        remaining = max(0, int((deadline - datetime.now(timezone.utc)).total_seconds())) if deadline else None
        record.update({
            "categories": [str(tag.get("name")) for tag in tags if isinstance(tag, dict) and tag.get("name")],
            "source_publication_status": "yet_to_publish" if str(item.get("is_pending", "")).casefold() == "yes" else "published",
            "estimated_publish_at": deadline.isoformat() if deadline else None,
            "countdown_captured_at": datetime.now(timezone.utc).isoformat() if deadline else None,
            "countdown_seconds_at_capture": remaining,
            "countdown_raw": str(expires) if deadline else None,
        })
    elif site.slug == "m3rx":
        title = str(item.get("title") or "").strip()
        host_match = re.fullmatch(
            r"(?:https?://)?(?:www\.)?((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})/?",
            title,
            re.I,
        )
        domain = host_match.group(1).casefold().removeprefix("www.") if host_match else None
        record.update({
            "domain": domain,
            "website": f"https://{domain}" if domain else None,
            "source_data_size": item.get("stolen"),
            "source_has_file_list": bool(item.get("list")),
        })
    return record


def _collect_d1r(site: ApiLeakSite, session: requests.Session) -> dict:
    """Fetch D1R's public WordPress listing pages using its published AJAX action."""
    errors = []
    pages = []
    try:
        bootstrap = session.get(site.url, timeout=PAGE_TIMEOUT)
        bootstrap.raise_for_status()
        nonce_match = re.search(r"var\s+myAjax\s*=\s*(\{[^;]+\})", bootstrap.text)
        if not nonce_match:
            raise ValueError("D1R listing page did not expose the public AJAX nonce")
        config = json.loads(nonce_match.group(1))
        nonce = config.get("nonce")
        if not nonce:
            raise ValueError("D1R AJAX configuration did not contain a nonce")
        total_pages = None
        seen_ids: set[str] = set()
        for page_number in range(1, MAX_PAGES + 1):
            response = session.post(
                site.endpoint,
                data={
                    "action": "mytheme_get_products_page",
                    "page_num": page_number,
                    "products_per_page": site.page_size,
                    "search": "",
                    "_wpnonce": nonce,
                },
                headers={"Referer": site.url, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
                timeout=PAGE_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not payload.get("success"):
                raise ValueError("D1R AJAX listing returned an unsuccessful response")
            data = payload.get("data") or {}
            items = data.get("products") if isinstance(data, dict) else None
            if not isinstance(items, list):
                raise ValueError("D1R AJAX response did not contain data.products")
            total = data.get("total_products") if isinstance(data, dict) else None
            if isinstance(total, int) and total >= 0:
                total_pages = ceil(total / site.page_size) if total else 0
            records = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                record = _normalized_record(site, item)
                if not record or record["source_record_id"] in seen_ids:
                    continue
                seen_ids.add(record["source_record_id"])
                records.append(record)
            pages.append({
                "url": response.url,
                "title": site.name,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", "application/json"),
                "records": records,
                "response_metadata": {"page": page_number, "page_size": site.page_size, "total": total},
            })
            if not items or (total_pages is not None and page_number >= total_pages):
                break
        else:
            errors.append(f"Pagination stopped at safety limit ({MAX_PAGES} pages)")
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        errors.append(f"{type(exc).__name__}: {str(exc)[:400]}")
    return {"site": site, "pages": pages, "pages_visited": len(pages), "errors": errors, "challenge": None}


def _collect_crypto24(site: ApiLeakSite, session: requests.Session) -> dict:
    """Bootstrap Crypto24's same-origin session and follow its totalPages API."""
    pages, errors = [], []
    seen_ids: set[str] = set()
    try:
        bootstrap = session.get(site.url, headers={"Accept": "text/html,application/xhtml+xml"}, timeout=PAGE_TIMEOUT)
        bootstrap.raise_for_status()
        origin = f"{urlsplit(site.url).scheme}://{urlsplit(site.url).netloc}"
        session.headers.update({"Origin": origin, "Referer": site.url, "Accept": "application/json, */*"})
        total_pages = None
        for page_number in range(1, MAX_PAGES + 1):
            response = session.get(site.endpoint, params={"page": page_number}, timeout=PAGE_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                raise ValueError("Crypto24 API response did not contain an items list")
            advertised = payload.get("totalPages")
            if isinstance(advertised, int) and advertised >= 0:
                total_pages = advertised
            records = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                record = _normalized_record(site, item)
                if not record:
                    continue
                record["source_publication_status"] = (
                    "published" if item.get("expired") is True
                    else "yet_to_publish" if item.get("expired") is False
                    else None
                )
                if record["source_record_id"] in seen_ids:
                    continue
                seen_ids.add(record["source_record_id"])
                records.append(record)
            pages.append({
                "url": response.url,
                "title": site.name,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", "application/json"),
                "records": records,
                "response_metadata": {"page": page_number, "page_size": len(items), "total_pages": total_pages},
            })
            if not items or (total_pages is not None and page_number >= total_pages):
                break
        else:
            errors.append(f"Pagination stopped at safety limit ({MAX_PAGES} pages)")
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors.append(f"{type(exc).__name__}: {str(exc)[:400]}")
    return {"site": site, "pages": pages, "pages_visited": len(pages), "errors": errors, "challenge": None}


def _collect_gunra(site: ApiLeakSite, session: requests.Session) -> dict:
    """Fetch Gunra's slow, single-response public company listing."""
    pages, errors = [], []
    try:
        response = session.get(site.endpoint, timeout=(30, 180))
        response.raise_for_status()
        payload = response.json()
        items = payload if isinstance(payload, list) else payload.get("companies", payload.get("data", [])) if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ValueError("Gunra API did not return a company list")
        records, seen_ids = [], set()
        for item in items:
            if not isinstance(item, dict):
                continue
            record = _normalized_record(site, item)
            if not record:
                continue
            record_id = record["source_record_id"]
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            records.append(record)
        pages.append({
            "url": response.url,
            "title": site.name,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "application/json"),
            "records": records,
            "response_metadata": {"returned_companies": len(items), "pagination": False},
        })
        if not records:
            errors.append("Gunra API returned no parseable company records")
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors.append(f"{type(exc).__name__}: {str(exc)[:400]}")
    return {"site": site, "pages": pages, "pages_visited": len(pages), "errors": errors, "challenge": None}


def _collect_lapsus(site: ApiLeakSite, session: requests.Session) -> dict:
    """Wait through Lapsus's short access queue, then read its public targets JSON."""
    import time
    from bs4 import BeautifulSoup

    pages, errors = [], []
    session.trust_env = False
    session.proxies.clear()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/json,*/*"})
    try:
        home = None
        for attempt in range(5):
            home = session.get(site.url, timeout=(45, 120))
            home.raise_for_status()
            soup = BeautifulSoup(home.text, "html.parser")
            title = soup.title.get_text(" ", strip=True).casefold() if soup.title else ""
            if "queue" not in title:
                break
            refresh = soup.select_one('meta[http-equiv="refresh" i]')
            wait_seconds = 10
            if refresh:
                match = re.match(r"\s*(\d+)", refresh.get("content", ""))
                if match:
                    wait_seconds = max(1, min(30, int(match.group(1)) + 1))
            time.sleep(wait_seconds)
        else:
            raise ValueError("Lapsus access queue did not release within five waits")

        headers = {"Accept": "application/json", "Referer": site.url}
        response = session.get(site.endpoint, headers=headers, timeout=(45, 120))
        if response.status_code == 403 and "not verified" in response.text.casefold():
            raise ValueError("Lapsus API still reports Not verified after the homepage queue released")
        response.raise_for_status()
        payload = response.json()
        items = _nested(payload, site.items_path)
        if not isinstance(items, list):
            raise ValueError("Lapsus API response did not contain a targets list")
        records, seen = [], set()
        for item in items:
            if not isinstance(item, dict):
                continue
            record = _normalized_record(site, item)
            if not record or record["source_record_id"] in seen:
                continue
            seen.add(record["source_record_id"])
            records.append(record)
        pages.append({
            "url": response.url,
            "title": site.name,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "application/json"),
            "records": records,
            "response_metadata": {"targets_returned": len(items), "pagination": False},
        })
        if not records:
            errors.append("Lapsus API returned no target records")
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors.append(f"{type(exc).__name__}: {str(exc)[:400]}")
    return {"site": site, "pages": pages, "pages_visited": len(pages), "errors": errors, "challenge": None}


def collect_api_site_pages(site: ApiLeakSite, tor_host: str, tor_port: int) -> dict:
    session = requests.Session()
    proxy = f"socks5h://{tor_host}:{tor_port}"
    session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({
        "Accept": "application/json, */*",
        "User-Agent": "DarkWolf-CTI/1.0",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": site.url,
    })

    if site.slug == "d1r":
        try:
            return _collect_d1r(site, session)
        finally:
            session.close()

    if site.slug == "crypto24":
        try:
            return _collect_crypto24(site, session)
        finally:
            session.close()

    if site.slug == "gunra":
        session.trust_env = False
        try:
            return _collect_gunra(site, session)
        finally:
            session.close()

    if site.slug == "lapsus":
        try:
            return _collect_lapsus(site, session)
        finally:
            session.close()

    pages = []
    errors = []
    seen_ids: set[str] = set()
    expected_pages = None
    try:
        if site.bootstrap_csrf:
            bootstrap = _session_get(
                session,
                site.url,
                verify_tls=site.verify_tls,
                headers={"Accept": "text/html,application/xhtml+xml"},
                timeout=_page_timeout_for_site(site),
            )
            bootstrap.raise_for_status()
            token_match = re.search(
                r'<meta\s+[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)',
                bootstrap.text,
                flags=re.IGNORECASE,
            ) or re.search(
                r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']csrf-token["\']',
                bootstrap.text,
                flags=re.IGNORECASE,
            )
            if not token_match:
                raise ValueError("Akira bootstrap page did not expose a CSRF meta token")
            session.headers["X-CSRF-Token"] = html.unescape(token_match.group(1))

        for page_number in range(1, MAX_PAGES + 1):
            params = {}
            if site.page_parameter:
                params[site.page_parameter] = page_number
            if site.page_size_parameter:
                params[site.page_size_parameter] = site.page_size
            if site.sort_parameter and site.sort_value:
                params[site.sort_parameter] = site.sort_value
            if site.extra_parameters:
                params.update(site.extra_parameters)
            response = _session_get(
                session,
                site.endpoint,
                verify_tls=site.verify_tls,
                params=params,
                timeout=PAGE_TIMEOUT,
            )
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()
            if "json" not in content_type and not (
                site.slug == "securotrop" and content_type.startswith("text/plain")
            ):
                raise ValueError(f"Expected JSON response; received {content_type or 'unknown content type'}")
            payload = response.json()
            items = payload if not site.items_path else _nested(payload, site.items_path)
            if not isinstance(items, list):
                raise ValueError(f"JSON response did not contain a list at {'.'.join(site.items_path)}")

            total = _nested(payload, site.total_path)
            if isinstance(total, int) and total >= 0:
                expected_pages = ceil(total / site.page_size) if total else 0

            records = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                record = _normalized_record(site, item)
                if not record or record["source_record_id"] in seen_ids:
                    continue
                seen_ids.add(record["source_record_id"])
                records.append(record)

            # Store normalized listing fields only; omit logos and download URLs.
            pages.append({
                "url": response.url,
                "title": site.name,
                "status_code": response.status_code,
                "content_type": content_type,
                "records": records,
                "response_metadata": {
                    "page": payload.get("page", page_number) if isinstance(payload, dict) else page_number,
                    "page_size": payload.get("pageSize", site.page_size) if isinstance(payload, dict) else len(items),
                    "total": total,
                },
            })

            if not items or (expected_pages is not None and page_number >= expected_pages):
                break
            if not site.supports_pagination:
                break
            if expected_pages is None and len(items) < site.page_size:
                break
        else:
            errors.append(f"Pagination stopped at safety limit ({MAX_PAGES} pages)")
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors.append(f"{type(exc).__name__}: {str(exc)[:400]}")
    finally:
        session.close()

    return {
        "site": site,
        "pages": pages,
        "pages_visited": len(pages),
        "errors": errors,
        "challenge": None,
    }
