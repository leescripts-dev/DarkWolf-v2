from app.events.detector import detect_events


def test_first_observation():

    comparison = {
        "changed": True,
        "change_type": "FIRST_OBSERVATION",
        "changed_fields": [],
        "changes": {},
    }

    events = detect_events(comparison)

    assert len(events) == 1
    assert events[0]["event_type"] == "VICTIM_DISCOVERED"


def test_proof_change():

    comparison = {
        "changed": True,
        "change_type": "CONTENT_CHANGED",
        "changed_fields": [
            "proof_ids"
        ],
        "changes": {
            "proof_ids": {
                "previous": ["A", "B"],
                "current": ["A", "B", "C"],
            }
        },
    }

    events = detect_events(comparison)

    assert len(events) == 1
    assert events[0]["event_type"] == "FILE_LIST_UPDATED"


def test_description_change():

    comparison = {
        "changed": True,
        "change_type": "CONTENT_CHANGED",
        "changed_fields": [
            "descriptions"
        ],
        "changes": {
            "descriptions": {
                "previous": ["Old"],
                "current": ["New"],
            }
        },
    }

    events = detect_events(comparison)

    assert len(events) == 1
    assert events[0]["event_type"] == "DESCRIPTION_CHANGED"


def test_unchanged():

    comparison = {
        "changed": False,
        "change_type": None,
        "changed_fields": [],
        "changes": {},
    }

    events = detect_events(comparison)

    assert events == []


if __name__ == "__main__":
    test_first_observation()
    test_proof_change()
    test_description_change()
    test_unchanged()

    print("All event tests passed.")