def compare_disclosures(
    previous: dict | None,
    current: dict,
) -> dict:

    fields = [
        "title",
        "categories",
        "content",
        "size",
        "leak_at",
        "cdn_id",
        "cdn_onion",
        "cdn_clear",
    ]

    # ---------------------------------------------------------
    # First observation / newly discovered disclosure
    # ---------------------------------------------------------
    if previous is None:
        changed_fields = []
        changes = {}

        for field in fields:
            current_value = current.get(field)

            # Do not report empty/null fields as newly added data.
            if current_value is None:
                continue

            if current_value == []:
                continue

            changed_fields.append(field)

            changes[field] = {
                "previous": None,
                "current": current_value,
            }

        return {
            "changed": True,
            "change_type": "FIRST_OBSERVATION",
            "changed_fields": changed_fields,
            "changes": changes,
        }

    # ---------------------------------------------------------
    # No change
    # ---------------------------------------------------------
    if previous.get("content_hash") == current.get("content_hash"):
        return {
            "changed": False,
            "change_type": None,
            "changed_fields": [],
            "changes": {},
        }

    # ---------------------------------------------------------
    # Existing disclosure changed
    # ---------------------------------------------------------
    changed_fields = []
    changes = {}

    for field in fields:
        previous_value = previous.get(field)
        current_value = current.get(field)

        if previous_value != current_value:
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