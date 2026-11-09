def _is_published_value(value) -> bool:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    positive = ("published", "publicly available", "data disclosed", "data leaked", "database leaked", "files leaked", "leak is available", "download available")
    pending = ("will be published", "awaiting publication", "pending exposure", "not yet published")
    for item in values:
        text = str(item or "").casefold()
        if any(term in text for term in pending):
            continue
        if any(term in text for term in positive):
            return True
    return False


def detect_events(
    comparison: dict,
) -> list[dict]:

    events = []

    change_type = comparison.get("change_type")

    # ---------------------------------------------
    # First observation
    # ---------------------------------------------

    if change_type == "FIRST_OBSERVATION":
        events.append(
            {
                "event_type": "VICTIM_DISCOVERED",
                "changed_fields": [],
                "changes": {},
                "details": {},
            }
        )

        return events

    # ---------------------------------------------
    # No meaningful change
    # ---------------------------------------------

    if not comparison.get("changed"):
        return events

    changed_fields = comparison.get(
        "changed_fields",
        [],
    )

    changes = comparison.get(
        "changes",
        {},
    )

    disclosure_fields = []
    publication_status = changes.get("source_publication_status", {})
    if isinstance(publication_status, dict):
        previous_status = str(publication_status.get("previous") or "").casefold()
        current_status = str(publication_status.get("current") or "").casefold()
        published_statuses = {"published", "disclosed", "leaked", "public", "exposed"}
        if current_status in published_statuses and previous_status not in published_statuses:
            disclosure_fields.append("source_publication_status")

    description_change = changes.get("descriptions", {})
    if isinstance(description_change, dict):
        if _is_published_value(description_change.get("current")) and not _is_published_value(description_change.get("previous")):
            disclosure_fields.append("descriptions")

    if disclosure_fields:
        events.append({
            "event_type": "DISCLOSURE_DISCOVERED",
            "changed_fields": disclosure_fields,
            "changes": {field: changes.get(field) for field in disclosure_fields},
            "details": {"publication_evidence": "source status or description changed to published/disclosed"},
        })

    # ---------------------------------------------
    # Field-specific events
    # ---------------------------------------------

    event_mapping = {
        "proof_ids": "FILE_LIST_UPDATED",
        "descriptions": "DESCRIPTION_CHANGED",
        "categories": "CATEGORY_CHANGED",
        "company_name": "VICTIM_NAME_CHANGED",
        "country": "VICTIM_COUNTRY_CHANGED",
        "revenue": "VICTIM_REVENUE_CHANGED",
        "logo_id": "LOGO_CHANGED",
        "leak_at": "LEAK_DATE_CHANGED",
        "source_publication_status": "PUBLICATION_STATUS_CHANGED",
        "cdn": "CDN_CHANGED",
    }

    for field in changed_fields:

        if field in disclosure_fields:
            continue

        event_type = event_mapping.get(field)

        if not event_type:
            continue

        events.append(
            {
                "event_type": event_type,
                "changed_fields": [field],
                "changes": {
                    field: changes.get(field)
                },
                "details": {},
            }
        )

    return events
