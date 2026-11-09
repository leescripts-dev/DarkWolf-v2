from app.snapshots.differ import compare_observations


def test_first_observation():
    current = {
        "content_hash": "abc"
    }

    result = compare_observations(
        previous=None,
        current=current,
    )

    assert result["change_type"] == "FIRST_OBSERVATION"


def test_unchanged():
    previous = {
        "content_hash": "abc",
        "proof_ids": ["A", "B"],
    }

    current = {
        "content_hash": "abc",
        "proof_ids": ["A", "B"],
    }

    result = compare_observations(
        previous=previous,
        current=current,
    )

    assert result["changed"] is False
    assert result["changes"] == {}


def test_proof_added():
    previous = {
        "content_hash": "abc",
        "proof_ids": ["A", "B"],
    }

    current = {
        "content_hash": "def",
        "proof_ids": ["A", "B", "C"],
    }

    result = compare_observations(
        previous=previous,
        current=current,
    )

    assert result["changed"] is True
    assert result["change_type"] == "CONTENT_CHANGED"
    assert "proof_ids" in result["changed_fields"]

    assert result["changes"]["proof_ids"]["previous"] == [
        "A",
        "B",
    ]

    assert result["changes"]["proof_ids"]["current"] == [
        "A",
        "B",
        "C",
    ]


def test_description_changed():
    previous = {
        "content_hash": "abc",
        "descriptions": [
            "Wait for files."
        ],
    }

    current = {
        "content_hash": "def",
        "descriptions": [
            "Files will be published soon."
        ],
    }

    result = compare_observations(
        previous=previous,
        current=current,
    )

    assert result["changed"] is True
    assert "descriptions" in result["changed_fields"]


if __name__ == "__main__":
    test_first_observation()
    test_unchanged()
    test_proof_added()
    test_description_changed()

    print("All differ tests passed.")