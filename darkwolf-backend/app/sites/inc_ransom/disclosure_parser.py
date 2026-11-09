from datetime import datetime, timezone
from urllib.parse import unquote

from app.sites.inc_ransom.disclosure_models import IncRansomDisclosure


def decode_text(value: str | None) -> str | None:
    if value is None:
        return None

    return unquote(value)


def decode_list(values: list[str] | None) -> list[str]:
    if not values:
        return []

    return [
        decode_text(value) or ""
        for value in values
    ]


def timestamp_to_datetime(value: int | None) -> datetime | None:
    if value is None or value <= 0:
        return None

    return datetime.fromtimestamp(
        value / 1000,
        tz=timezone.utc,
    )


def extract_size(content: list[str]) -> str | None:
    for item in content:
        decoded = decode_text(item)

        if not decoded:
            continue

        if decoded.lower().startswith("size:"):
            return decoded.split(":", 1)[1].strip()

    return None


def parse_disclosure(
    data: dict,
    announcement_id: str,
) -> IncRansomDisclosure:

    content = decode_list(
        data.get("content")
    )

    categories = decode_list(
        data.get("categories")
    )

    cdn = data.get("cdn") or {}

    return IncRansomDisclosure(
        id=data["_id"],
        announcement_id=announcement_id,

        title=decode_text(
            data.get("title")
        ) or "",

        categories=categories,
        content=content,

        size=extract_size(content),

        leak_at=timestamp_to_datetime(
            data.get("leakAt")
        ),

        created_at=timestamp_to_datetime(
            data.get("createdAt")
        ),

        cdn_id=cdn.get("_id"),

        cdn_onion=decode_text(
            cdn.get("onion")
        ),

        cdn_clear=decode_text(
            cdn.get("clear")
        ),
    )