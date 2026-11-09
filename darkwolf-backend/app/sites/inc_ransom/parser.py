from datetime import datetime, timezone
from urllib.parse import unquote

from app.sites.inc_ransom.models import (
    IncRansomAnnouncement,
    IncRansomCompany,
)


def timestamp_to_datetime(
    value: int | None,
) -> datetime | None:

    if value is None or value <= 0:
        return None

    return datetime.fromtimestamp(
        value / 1000,
        tz=timezone.utc,
    )


def decode_text(
    value: str | None,
) -> str | None:

    if value is None:
        return None

    return unquote(value)


def parse_announcement(
    data: dict,
    existing_country: str | None = None,
) -> IncRansomAnnouncement:

    company_data = data.get("company", {})

    company = IncRansomCompany(
        id=company_data.get("_id"),

        name=(
            decode_text(
                company_data.get("company_name")
            )
            or ""
        ),

        country=(
            existing_country
            or company_data.get("country")
        ),

        revenue=company_data.get("revenue"),
    )

    descriptions = [
        decode_text(description) or ""
        for description in data.get(
            "description",
            [],
        )
    ]

    return IncRansomAnnouncement(
        id=data["_id"],

        company=company,

        categories=data.get(
            "categories",
            [],
        ),

        descriptions=descriptions,

        logo_id=data.get("logo"),

        proof_ids=data.get(
            "proof",
            [],
        ),

        password_hash=data.get(
            "password"
        ),

        visits=data.get("visits"),

        leak_at=timestamp_to_datetime(
            data.get("leakAt")
        ),

        created_at=timestamp_to_datetime(
            data.get("createdAt")
        ),

        updated_at=timestamp_to_datetime(
            data.get("updatedAt")
        ),

        cdn=data.get("cdn"),
    )