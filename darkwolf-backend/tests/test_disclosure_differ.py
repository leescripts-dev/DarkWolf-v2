from app.snapshots.disclosure_differ import compare_disclosures


BASE = {
    "title": "Disclosure of data :",
    "categories": [
        "Contracts",
        "Confidential",
        "Financial data",
    ],
    "content": [
        "Size:29gb",
    ],
    "size": "29gb",
    "leak_at": None,
    "cdn_id": "cdn-001",
    "cdn_onion": "http://example.onion",
    "cdn_clear": "http://example.org",
    "content_hash": "hash-001",
}


def test_first_observation():
    result = compare_disclosures(
        previous=None,
        current=BASE,
    )

    assert result["changed"] is True
    assert result["change_type"] == "FIRST_OBSERVATION"


def test_unchanged():
    result = compare_disclosures(
        previous=BASE,
        current=BASE.copy(),
    )

    assert result["changed"] is False
    assert result["change_type"] is None
    assert result["changed_fields"] == []


def test_size_changed():
    current = BASE.copy()
    current["size"] = "42gb"
    current["content_hash"] = "hash-002"

    result = compare_disclosures(
        previous=BASE,
        current=current,
    )

    assert result["changed"] is True
    assert result["change_type"] == "CONTENT_CHANGED"

    assert result["changed_fields"] == [
        "size"
    ]

    assert result["changes"]["size"] == {
        "previous": "29gb",
        "current": "42gb",
    }


def test_categories_changed():
    current = BASE.copy()
    current["categories"] = [
        "Contracts",
        "Confidential",
        "Financial data",
        "Source code",
    ]
    current["content_hash"] = "hash-003"

    result = compare_disclosures(
        previous=BASE,
        current=current,
    )

    assert result["changed_fields"] == [
        "categories"
    ]


def test_content_changed():
    current = BASE.copy()
    current["content"] = [
        "Size:42gb",
        "Source code",
    ]
    current["content_hash"] = "hash-004"

    result = compare_disclosures(
        previous=BASE,
        current=current,
    )

    assert result["changed_fields"] == [
        "content"
    ]


def main():
    test_first_observation()
    test_unchanged()
    test_size_changed()
    test_categories_changed()
    test_content_changed()

    print("All disclosure differ tests passed.")


if __name__ == "__main__":
    main()