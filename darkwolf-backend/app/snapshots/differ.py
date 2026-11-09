from datetime import datetime, timezone


def _comparison_value(value):
    """Normalize BSON's naive UTC datetimes against timezone-aware app values."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return value


def compare_observations(
    previous: dict | None,
    current: dict,
) -> dict:

    # ---------------------------------------------
    # First observation
    # ---------------------------------------------

    if previous is None:
        return {
            "changed": True,
            "change_type": "FIRST_OBSERVATION",
            "changed_fields": [],
            "changes": {},
        }

    # ---------------------------------------------
    # Fast path: no content change
    # ---------------------------------------------

    if previous.get("content_hash") == current.get("content_hash"):
        return {
            "changed": False,
            "change_type": None,
            "changed_fields": [],
            "changes": {},
        }

    # ---------------------------------------------
    # Fields that represent actual content
    # ---------------------------------------------

    fields = [
        "company_name",
        "company_id",
        "country",
        "revenue",
        "categories",
        "descriptions",
        "proof_ids",
        "logo_id",
        "leak_at",
        "source_publication_status",
        "cdn",
    ]

    changed_fields = []
    changes = {}

    for field in fields:
        previous_value = previous.get(field)
        current_value = current.get(field)

        if _comparison_value(previous_value) != _comparison_value(current_value):
            changed_fields.append(field)

            changes[field] = {
                "previous": previous_value,
                "current": current_value,
            }

    return {
        "changed": True,
        "change_type": "CONTENT_CHANGED",
        "changed_fields": changed_fields,
        "changes": changes,
    }
