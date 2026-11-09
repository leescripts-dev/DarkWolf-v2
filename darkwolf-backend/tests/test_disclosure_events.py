from app.events.disclosure_detector import (
    detect_disclosure_events,
)


def test_first_observation():
    comparison = {
        "changed": True,
        "change_type": "FIRST_OBSERVATION",
        "changed_fields": [],
        "changes": {},
    }

    events = detect_disclosure_events(
        comparison
    )

    assert len(events) == 1
    assert events[0]["event_type"] == (
        "DISCLOSURE_DISCOVERED"
    )


def test_unchanged():
    comparison = {
        "changed": False,
        "change_type": None,
        "changed_fields": [],
        "changes": {},
    }

    events = detect_disclosure_events(
        comparison
    )

    assert events == []


def test_size_changed():
    comparison = {
        "changed": True,
        "change_type": "CONTENT_CHANGED",
        "changed_fields": ["size"],
        "changes": {
            "size": {
                "previous": "29gb",
                "current": "42gb",
            }
        },
    }

    events = detect_disclosure_events(
        comparison
    )

    assert len(events) == 1
    assert events[0]["event_type"] == (
        "DISCLOSURE_SIZE_CHANGED"
    )

    assert events[0]["changes"]["size"] == {
        "previous": "29gb",
        "current": "42gb",
    }


def test_multiple_changes():
    comparison = {
        "changed": True,
        "change_type": "CONTENT_CHANGED",
        "changed_fields": [
            "size",
            "categories",
            "content",
        ],
        "changes": {
            "size": {
                "previous": "29gb",
                "current": "42gb",
            },
            "categories": {
                "previous": ["Financial data"],
                "current": [
                    "Financial data",
                    "Source code",
                ],
            },
            "content": {
                "previous": ["Size:29gb"],
                "current": [
                    "Size:42gb",
                    "Source code",
                ],
            },
        },
    }

    events = detect_disclosure_events(
        comparison
    )

    event_types = {
        event["event_type"]
        for event in events
    }

    assert event_types == {
        "DISCLOSURE_SIZE_CHANGED",
        "DISCLOSURE_CATEGORIES_CHANGED",
        "DISCLOSURE_CONTENT_CHANGED",
    }


def test_cdn_change_generates_one_event():
    comparison = {
        "changed": True,
        "change_type": "CONTENT_CHANGED",
        "changed_fields": [
            "cdn_id",
            "cdn_onion",
        ],
        "changes": {
            "cdn_id": {
                "previous": "cdn-1",
                "current": "cdn-2",
            },
            "cdn_onion": {
                "previous": "http://old.onion",
                "current": "http://new.onion",
            },
        },
    }

    events = detect_disclosure_events(
        comparison
    )

    assert len(events) == 1
    assert events[0]["event_type"] == (
        "DISCLOSURE_CDN_CHANGED"
    )

    assert set(events[0]["changed_fields"]) == {
        "cdn_id",
        "cdn_onion",
    }


def main():
    test_first_observation()
    test_unchanged()
    test_size_changed()
    test_multiple_changes()
    test_cdn_change_generates_one_event()

    print("All disclosure event tests passed.")


if __name__ == "__main__":
    main()