"""Recon leak-site listing pages over Tor. Structure only; no dump downloads."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from openpyxl import load_workbook

TOR = "socks5h://127.0.0.1:9050"
PROXIES = {"http": TOR, "https": TOR}
TIMEOUT = 45
ROOT = Path(__file__).resolve().parent
OUT = ROOT
OUT.mkdir(exist_ok=True)
HTML_DIR = OUT / "html"
HTML_DIR.mkdir(exist_ok=True)

CAPTCHA_HINTS = [
    "captcha",
    "recaptcha",
    "hcaptcha",
    "h-captcha",
    "g-recaptcha",
    "cf-turnstile",
    "turnstile",
    "challenges.cloudflare.com",
    "cdn-cgi/challenge",
    "checking your browser",
    "just a moment",
    "verify you are human",
    "attention required",
    "ddos-guard",
]

API_PATH_RE = re.compile(
    r"""(?:["'`])(/?(?:api|graphql|backend|ajax|data|leaks?|posts?|announcements?|companies|victims?|blog|news|campaigns|catalog)[^"'`\s]{0,120})""",
    re.I,
)
SCRIPT_SRC_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.I)
LINK_RE = re.compile(r'<(?:a|link)[^>]+href=["\']([^"\']+)["\']', re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
JSON_ASSIGN_RE = re.compile(
    r"(?:window\.__[A-Z_]+|var\s+data|const\s+data)\s*=\s*(\{.*?\}|\[.*?\]);",
    re.S,
)

COMMON_API_PATHS = [
    "/api",
    "/api/",
    "/api/v1",
    "/api/posts",
    "/api/leaks",
    "/api/announcements",
    "/api/companies",
    "/announcements",
    "/leaks",
    "/data.json",
    "/posts.json",
    "/companies.json",
    "/blog.json",
]


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    raw = raw.replace("http:/", "http://", 1) if raw.startswith("http:/") and not raw.startswith("http://") else raw
    if raw.startswith("https:/") and not raw.startswith("https://"):
        raw = "https://" + raw[len("https:/") :]
    if not raw.startswith("http"):
        raw = "http://" + raw.lstrip("/")
    return raw


def load_sites() -> list[dict]:
    wb = load_workbook(ROOT / "inventory" / "Leak Sites.xlsx", data_only=True)
    ws = wb.active
    sites = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        name, link = row[0], row[1]
        if not name or not link:
            continue
        sites.append({"name": str(name).strip(), "url": normalize_url(str(link))})
    return sites


def sniff_captcha(text: str, headers: dict) -> list[str]:
    blob = (text or "").lower()
    hits = [h for h in CAPTCHA_HINTS if h in blob]
    server = (headers.get("server") or "").lower()
    if "cloudflare" in server and ("cf-ray" in {k.lower() for k in headers} or "just a moment" in blob):
        hits.append("cloudflare-server")
    return sorted(set(hits))


def layout_signals(html: str) -> dict:
    low = html.lower()
    return {
        "has_table": "<table" in low,
        "has_cards_class": bool(re.search(r'class=["\'][^"\']*(card|victim|leak|company|post)[^"\']*["\']', low)),
        "has_react": "react" in low or "data-reactroot" in low or "__NEXT_DATA__" in html,
        "has_vue": "vue" in low or "id=\"app\"" in low,
        "has_angular": "ng-app" in low or "ng-version" in low,
        "has_next": "__NEXT_DATA__" in html,
        "has_nuxt": "__NUXT__" in html,
        "inline_json_script": bool(re.search(r'<script[^>]+type=["\']application/json', low)),
        "script_count": len(SCRIPT_SRC_RE.findall(html)),
        "external_scripts": SCRIPT_SRC_RE.findall(html)[:30],
        "api_paths_in_html": sorted(set(API_PATH_RE.findall(html)))[:40],
        "internal_hrefs": sorted(
            {
                h
                for h in LINK_RE.findall(html)
                if h.startswith("/") or ".onion" in h or h.startswith("?")
            }
        )[:40],
        "looks_empty_spa": len(re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)) < 1500
        and len(SCRIPT_SRC_RE.findall(html)) > 0,
    }


def fetch(url: str) -> requests.Response:
    return requests.get(
        url,
        proxies=PROXIES,
        timeout=TIMEOUT,
        allow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:128.0) Gecko/20100101 Firefox/128.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )


def try_json(url: str) -> dict | None:
    try:
        r = requests.get(
            url,
            proxies=PROXIES,
            timeout=20,
            headers={"Accept": "application/json, text/plain, */*"},
        )
        ctype = (r.headers.get("content-type") or "").lower()
        snippet = r.text[:400]
        parsed = None
        if "json" in ctype or r.text[:1] in "{[":
            try:
                parsed = r.json()
            except Exception:
                parsed = None
        return {
            "url": url,
            "status": r.status_code,
            "content_type": ctype,
            "bytes": len(r.content),
            "json_type": type(parsed).__name__ if parsed is not None else None,
            "json_keys": list(parsed.keys())[:30] if isinstance(parsed, dict) else None,
            "json_len": len(parsed) if isinstance(parsed, list) else None,
            "snippet": snippet,
        }
    except Exception as exc:
        return {"url": url, "error": str(exc)}


def probe_site(site: dict) -> dict:
    name = site["name"]
    url = site["url"]
    result = {
        "name": name,
        "url": url,
        "ok": False,
        "captcha": False,
        "captcha_hints": [],
        "error": None,
    }
    t0 = time.time()
    try:
        r = fetch(url)
        html = r.text or ""
        elapsed = round(time.time() - t0, 2)
        title_m = TITLE_RE.search(html)
        title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else None
        hints = sniff_captcha(html, dict(r.headers))
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60]
        html_path = HTML_DIR / f"{slug}.html"
        html_path.write_text(html[:250_000], encoding="utf-8", errors="replace")

        result.update(
            {
                "ok": True,
                "final_url": str(r.url),
                "status": r.status_code,
                "elapsed_s": elapsed,
                "content_type": r.headers.get("content-type"),
                "server": r.headers.get("server"),
                "bytes": len(r.content),
                "title": title,
                "captcha_hints": hints,
                "captcha": bool(hints),
                "html_file": str(html_path),
                "layout": layout_signals(html),
            }
        )

        if not result["captcha"]:
            origin = f"{urlparse(str(r.url)).scheme}://{urlparse(str(r.url)).netloc}"
            api_hits = []
            for path in COMMON_API_PATHS:
                hit = try_json(urljoin(origin + "/", path.lstrip("/")))
                if hit and hit.get("status") in (200, 201) and (
                    hit.get("json_type") in ("dict", "list") or "json" in (hit.get("content_type") or "")
                ):
                    api_hits.append(hit)
            result["api_probes"] = api_hits

            scripts = result["layout"]["external_scripts"][:5]
            js_apis = []
            for src in scripts:
                abs_src = urljoin(str(r.url), src)
                if not abs_src.startswith("http"):
                    continue
                try:
                    js = requests.get(abs_src, proxies=PROXIES, timeout=25).text
                    found = sorted(set(API_PATH_RE.findall(js)))[:40]
                    if found:
                        js_apis.append({"script": abs_src, "paths": found})
                except Exception:
                    continue
            result["js_api_paths"] = js_apis
    except Exception as exc:
        result["error"] = str(exc)
        result["elapsed_s"] = round(time.time() - t0, 2)
    return result


def main() -> None:
    sites = load_sites()
    print(f"Loaded {len(sites)} sites", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(probe_site, s): s["name"] for s in sites}
        done = 0
        for fut in as_completed(futs):
            done += 1
            rec = fut.result()
            results.append(rec)
            flag = "CAPTCHA" if rec.get("captcha") else ("OK" if rec.get("ok") else "FAIL")
            print(
                f"[{done}/{len(sites)}] {flag} {rec['name']} status={rec.get('status')} err={rec.get('error')}",
                flush=True,
            )
    results.sort(key=lambda x: x["name"].lower())
    (OUT / "probe_results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print("Wrote", OUT / "probe_results.json", flush=True)


if __name__ == "__main__":
    main()
