import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
results = json.loads((ROOT / "probe_results.json").read_text(encoding="utf-8"))
html_dir = ROOT / "html"

WP = re.compile(r"wp-content|wordpress|wp-includes", re.I)
BOOTSTRAP = re.compile(r"bootstrap", re.I)
CARD = re.compile(r'class=["\'][^"\']*(card|victim|company|leak-item|post|news-card)[^"\']*', re.I)
TABLE = re.compile(r"<table", re.I)
FETCH = re.compile(r"fetch\(|axios|XMLHttpRequest|/api/", re.I)
JSON_EMBED = re.compile(r"<script[^>]*>\s*(?:window\.)?\w+\s*=\s*[\[{]", re.I)
PHP = re.compile(r"\.php(\?|$|/)", re.I)
NEXT = re.compile(r"__NEXT_DATA__|/_next/", re.I)
VUE = re.compile(r"vue\.js|id=[\"']app[\"']", re.I)
REACT = re.compile(r"react|data-reactroot", re.I)


def classify(rec):
    if rec.get("captcha"):
        return "captcha"
    if not rec.get("ok"):
        err = rec.get("error") or ""
        if "SSL" in err or "certificate" in err:
            return "https_ssl_fail"
        if "Host unreachable" in err or "0x04" in err:
            return "offline_unreachable"
        if "timed out" in err.lower() or "ConnectTimeout" in err:
            return "offline_timeout"
        if "0x01" in err:
            return "socks_fail"
        return "fail_other"

    path = rec.get("html_file")
    html = Path(path).read_text(encoding="utf-8", errors="replace") if path and Path(path).exists() else ""
    layout = rec.get("layout") or {}
    api = rec.get("api_probes") or []
    js_api = rec.get("js_api_paths") or []
    real_api = [a for a in api if a.get("json_type") in ("dict", "list")]

    if real_api:
        return "json_api"
    if layout.get("looks_empty_spa") or layout.get("has_react") or layout.get("has_next") or layout.get("has_vue"):
        return "js_spa"
    if WP.search(html):
        return "wordpress_html"
    if TABLE.search(html) and not layout.get("looks_empty_spa"):
        return "static_html_table"
    if CARD.search(html) or layout.get("has_cards_class"):
        return "static_html_cards"
    if PHP.search(html) or (rec.get("url") or "").endswith(".php") or "/index.php" in (rec.get("url") or ""):
        return "php_server_rendered"
    if FETCH.search(html) or js_api:
        return "js_hydrated"
    if rec.get("bytes", 0) < 2500:
        return "thin_shell"
    return "static_html_misc"


groups = defaultdict(list)
for rec in results:
    groups[classify(rec)].append(rec)

print("COUNTS")
for k in sorted(groups, key=lambda x: -len(groups[x])):
    print(f"  {k}: {len(groups[k])}")
print()
for k, recs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    print(f"=== {k} ({len(recs)}) ===")
    for r in recs:
        extra = ""
        if r.get("captcha"):
            extra = " hints=" + ",".join(r.get("captcha_hints") or [])
        if r.get("error"):
            extra = " " + (r["error"][:90].replace("\n", " "))
        apis = r.get("api_probes") or []
        if apis:
            extra += " APIs=" + ",".join(a.get("url", "")[-40:] for a in apis[:3])
        print(f"  - {r['name']}: status={r.get('status')} title={r.get('title')!r} bytes={r.get('bytes')}{extra}")
    print()
