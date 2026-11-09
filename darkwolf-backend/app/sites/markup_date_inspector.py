from datetime import datetime
import json
import re

from bs4 import BeautifulSoup


_DATE_PATTERNS = (
    re.compile(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}(?:[T ][0-2]?\d:[0-5]\d(?::[0-5]\d)?(?:\.\d+)?(?:Z|[+-][0-2]\d:?\d\d)?)?\b", re.I),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2}\b", re.I),
    re.compile(r"\b\d{1,2}/\d{1,2}/20\d{2}\b"),
)


def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_date(value: str) -> str | None:
    value = value.strip()
    for pattern in _DATE_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        candidate = match.group(0)
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            for date_format in ("%Y/%m/%d", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y", "%m/%d/%Y"):
                try:
                    parsed = datetime.strptime(candidate, date_format)
                    break
                except ValueError:
                    parsed = None
            if parsed is None:
                continue
        return parsed.date().isoformat()
    return None


def _is_hidden(node) -> bool:
    for current in (node, *node.parents):
        if not getattr(current, "attrs", None):
            continue
        style = (current.get("style") or "").casefold().replace(" ", "")
        classes = " ".join(current.get("class", []))
        if (
            current.has_attr("hidden")
            or (current.get("aria-hidden") or "").casefold() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
            or bool(re.search(r"\b(hidden|invisible|d-none|sr-only)\b", classes, re.I))
        ):
            return True
    return False


def _jsonld_candidates(soup: BeautifulSoup, wanted: str) -> list[dict]:
    found = []

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            names = [value.get(key) for key in ("name", "legalName", "headline")]
            if any(isinstance(item, str) and _normalize_name(item) == wanted for item in names):
                for key in ("datePublished", "dateCreated", "dateModified", "uploadDate"):
                    date_value = value.get(key)
                    if isinstance(date_value, str):
                        found.append({
                            "value": date_value,
                            "attribute": key,
                            "tag": "script[type=application/ld+json]",
                            "class_name": "",
                            "hidden": True,
                            "value_visible_in_text": False,
                        })
            for item in value.values():
                visit(item)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            visit(json.loads(script.string or script.get_text()))
        except (TypeError, ValueError):
            continue
    return found


def inspect_markup_dates(html_source: str, records: list[dict]) -> dict:
    """Find record-scoped dates in markup, including hidden nodes and attributes.

    Candidates are retained as evidence only. They are not promoted to leak dates
    automatically because generic created/published fields can mean different
    things on different sources (for example, Qilin post dates and countdowns).
    """
    soup = BeautifulSoup(html_source or "", "html.parser")
    title_selector = "h1,h2,h3,h4,h5,a,td,[class*=title i],[class*=name i]"
    records_with_date = 0
    hidden_date_records = 0
    for record in records:
        organization = record.get("organization", "")
        wanted = _normalize_name(organization)
        title_nodes = [
            node for node in soup.select(title_selector)
            if _normalize_name(node.get_text(" ", strip=True)) == wanted
        ][:5]
        candidates = []
        for title in title_nodes:
            scope = title
            for ancestor in title.parents:
                if ancestor.name in {"body", "html"}:
                    break
                text = ancestor.get_text(" ", strip=True)
                marker = f"{ancestor.name} {' '.join(ancestor.get('class', []))}"
                if len(text) <= 3000 and re.search(r"article|tr|li|card|item|victim|company|post|entry|leak", marker, re.I):
                    scope = ancestor
                    break

            nodes = [scope, *scope.find_all(True, limit=1499)]
            for node in nodes:
                class_name = " ".join(node.get("class", []))
                visible_text = node.get_text(" ", strip=True)
                hidden = _is_hidden(node)
                for attr, value in node.attrs.items():
                    attr_name = str(attr).casefold()
                    if not re.search(r"date|time|created|published|posted|leak|release|disclos|timestamp", attr_name, re.I):
                        continue
                    if re.search(r"countdown|timer|deadline|expire|remaining|duration|estimate", attr_name, re.I):
                        continue
                    for raw_value in value if isinstance(value, list) else [value]:
                        if isinstance(raw_value, str) and raw_value.strip():
                            candidates.append({
                                "value": raw_value.strip(),
                                "attribute": attr_name,
                                "tag": node.name,
                                "class_name": class_name[:180],
                                "hidden": hidden,
                                "value_visible_in_text": raw_value.strip() in visible_text,
                            })
                if node.name == "meta" and re.search(r"date|published|created", str(node.get("property") or node.get("itemprop") or ""), re.I):
                    candidates.append({
                        "value": node.get("content", ""),
                        "attribute": node.get("property") or node.get("itemprop"),
                        "tag": node.name,
                        "class_name": class_name[:180],
                        "hidden": True,
                        "value_visible_in_text": False,
                    })
                if node.name == "time" or re.search(r"\b(date|published|posted|leak-date|created-at)\b", class_name, re.I):
                    value = node.get("datetime") or node.get("data-date") or visible_text
                    if value:
                        candidates.append({
                            "value": value,
                            "attribute": "datetime" if node.get("datetime") else "data-date" if node.get("data-date") else "text",
                            "tag": node.name,
                            "class_name": class_name[:180],
                            "hidden": hidden,
                            "value_visible_in_text": value in visible_text,
                        })
                if hidden:
                    for match in _DATE_PATTERNS:
                        for date_match in match.finditer(visible_text):
                            candidates.append({
                                "value": date_match.group(0),
                                "attribute": "hidden_text",
                                "tag": node.name,
                                "class_name": class_name[:180],
                                "hidden": True,
                                "value_visible_in_text": False,
                            })
        candidates.extend(_jsonld_candidates(soup, wanted))
        valid = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            raw_value = candidate.get("value")
            if not isinstance(raw_value, str):
                continue
            normalized = _normalize_date(raw_value)
            if not normalized:
                continue
            item = {**candidate, "normalized_date": normalized}
            valid.append(item)
        # Keep distinct candidates only; repeated attributes are common on
        # framework-generated markup and are not useful as duplicate evidence.
        unique = {}
        for item in valid:
            key = (item.get("normalized_date"), item.get("attribute"), item.get("tag"))
            unique.setdefault(key, item)
        record["markup_date_candidates"] = list(unique.values())
        hidden_candidates = [
            item for item in unique.values()
            if item.get("hidden")
        ]
        if unique:
            records_with_date += 1
        if hidden_candidates:
            hidden_date_records += 1

    return {
        "records_checked": len(records),
        "records_with_markup_date": records_with_date,
        "hidden_date_records": hidden_date_records,
        "date_candidates_missing_from_extraction": sum(
            bool(record.get("markup_date_candidates")) and not record.get("listed_date")
            for record in records
        ),
        "hidden_date_missing_from_ui_records": sum(
            bool(record.get("markup_date_candidates"))
            and not record.get("listed_date")
            and any(item.get("hidden") for item in record["markup_date_candidates"])
            for record in records
        ),
    }
