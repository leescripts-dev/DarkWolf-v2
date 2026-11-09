def detect_disclosure_events(
    comparison: dict,
) -> list[dict]:

    events = []

    change_type = comparison.get(
        "change_type"
    )

    changed_fields = comparison.get(
        "changed_fields",
        [],
    )

    changes = comparison.get(
        "changes",
        {},
    )

    # ---------------------------------------------------------
    # Newly discovered disclosure
    # ---------------------------------------------------------
    if change_type == "FIRST_OBSERVATION":
        events.append({
            "event_type": "DISCLOSURE_DISCOVERED",
            "changed_fields": changed_fields,
            "changes": changes,
            "details": {},
        })

        return events

    # ---------------------------------------------------------
    # No change
    # ---------------------------------------------------------
    if not comparison.get("changed"):
        return events

    # ---------------------------------------------------------
    # Existing disclosure changed
    # ---------------------------------------------------------
    event_mapping = {
        "title": "DISCLOSURE_TITLE_CHANGED",
        "categories": "DISCLOSURE_CATEGORIES_CHANGED",
        "content": "DISCLOSURE_CONTENT_CHANGED",
        "size": "DISCLOSURE_SIZE_CHANGED",
        "leak_at": "DISCLOSURE_LEAK_DATE_CHANGED",
        "cdn_id": "DISCLOSURE_CDN_CHANGED",
        "cdn_onion": "DISCLOSURE_CDN_CHANGED",
        "cdn_clear": "DISCLOSURE_CDN_CHANGED",
    }

    generated_event_types = set()

    for field in changed_fields:
        event_type = event_mapping.get(field)

        if not event_type:
            continue

        # CDN has three possible fields but should
        # generate only one event.
        if event_type in generated_event_types:
            continue

        generated_event_types.add(event_type)

        event_fields = [
            field
            for field in changed_fields
            if event_mapping.get(field) == event_type
        ]

        event_changes = {
            field: changes.get(field)
            for field in event_fields
        }

        events.append({
            "event_type": event_type,
            "changed_fields": event_fields,
            "changes": event_changes,
            "details": {},
        })

    return events