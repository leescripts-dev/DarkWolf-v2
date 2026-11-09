"""Lightweight first-page inspection for workbook sites not in old recon."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parent.parent
RECON_ROOT = Path(__file__).resolve().parent
OUT = RECON_ROOT / "new_site_probe_results.json"
HTML_DIR = RECON_ROOT / "html_new_sites"
HTML_DIR.mkdir(exist_ok=True)
PROXY = "socks5h://127.0.0.1:9050"
CAPTCHA_MARKERS = (
    "captcha", "hcaptcha", "recaptcha", "cf-turnstile", "turnstile",
    "verify you are human", "checking your browser", "proof of work",
    "ddos-guard", "challenge-platform", "access denied",
)


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def normalize_url(raw: str) -> str:
    raw = raw.strip().replace("\n", " ")
    match = re.search(r"https?://[^\s]+", raw, re.I)
    if match:
        raw = match.group(0)
        # Workbook contains one duplicated URL pasted into a single cell.
        raw = re.sub(r"(https?://[^\s]+)\1$", r"\1", raw, flags=re.I)
    else:
        host = re.search(r"[a-z2-7]{16,56}\.onion", raw, re.I)
        if not host:
            return raw
        raw = "http://" + host.group(0)
    return raw.rstrip("\"' ")


def load_targets() -> list[dict]:
    old = json.loads((RECON_ROOT / "probe_results.json").read_text(encoding="utf-8"))
    old_names = {normalize(row["name"]) for row in old}
    workbook = load_workbook(RECON_ROOT / "inventory" / "Leak Sites.xlsx", read_only=True, data_only=True)
    targets = []
    seen = set()
    for name, link, *_ in workbook.active.iter_rows(min_row=2, values_only=True):
        if not name or not link or normalize(str(name)) in old_names:
            continue
        url = normalize_url(str(link))
        if not url.startswith(("http://", "https://")):
            continue
        key = normalize(str(name))
        if key in seen:
            continue
        seen.add(key)
        targets.append({"name": str(name).strip(), "url": url})
    return targets


def inspect(site: dict) -> dict:
    result = {**site, "ok": False, "captcha": False, "errors": []}
    started = time.time()
    try:
        response = requests.get(
            site["url"],
            proxies={"http": PROXY, "https": PROXY},
            timeout=(12, 24),
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            },
        )
        body = response.text[:500_000]
        low = body.casefold()
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else None
        hints = [marker for marker in CAPTCHA_MARKERS if marker in low]
        scripts = re.findall(r"<script\b[^>]*\bsrc=[\"']([^\"']+)", body, re.I)
        classes = re.findall(r"class=[\"']([^\"']+)", body, re.I)
        text = re.sub(r"<script\b[^>]*>[\s\S]*?</script>|<style\b[^>]*>[\s\S]*?</style>", " ", body, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        html_path = HTML_DIR / f"{normalize(site['name'])}.html"
        html_path.write_text(body, encoding="utf-8", errors="replace")
        result.update({
            "ok": response.status_code < 500,
            "status": response.status_code,
            "final_url": response.url,
            "title": title,
            "content_type": response.headers.get("content-type"),
            "elapsed_seconds": round(time.time() - started, 2),
            "captcha": bool(hints),
            "captcha_hints": hints,
            "script_count": len(scripts),
            "scripts": scripts[:12],
            "has_api_words": bool(re.search(r"api|graphql|fetch\(|axios|\.json", low)),
            "has_vue_react_angular": bool(re.search(r"react|vue|angular|__next_data__|__nuxt__", low)),
            "has_tables": bool(re.search(r"<table\b", low)),
            "card_classes": [c for c in classes if re.search(r"card|victim|leak|company|target|post|entry", c, re.I)][:20],
            "heading_count": len(re.findall(r"<h[1-4]\b", body, re.I)),
            "anchor_count": len(re.findall(r"<a\b[^>]+href", body, re.I)),
            "visible_text_preview": text[:1400],
            "html_file": str(html_path),
        })
    except Exception as exc:
        result.update({"elapsed_seconds": round(time.time() - started, 2), "error": f"{type(exc).__name__}: {str(exc)[:400]}"})
    return result


def main() -> None:
    targets = load_targets()
    print(f"Inspecting {len(targets)} sites", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(inspect, site): site["name"] for site in targets}
        for index, future in enumerate(as_completed(futures), 1):
            row = future.result()
            results.append(row)
            state = "CAPTCHA" if row["captcha"] else ("OK" if row["ok"] else "FAIL")
            print(f"[{index}/{len(targets)}] {state} {row['name']} status={row.get('status')} error={row.get('error')}", flush=True)
    results.sort(key=lambda row: row["name"].casefold())
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
