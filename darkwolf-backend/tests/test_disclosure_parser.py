from app.sites.inc_ransom.disclosure_parser import parse_disclosure


SAMPLE_DISCLOSURE = {
    "_id": "6abac1d8366c46847ef8e876",
    "announcement": "6abab9929cd108bf261f2fdd",
    "title": "Disclosure%20of%20data%20%3A",
    "categories": [
        "Contracts",
        "Confidential",
        "Financial%20data",
        "Customer's%20data",
        "Incidents",
        "HR",
    ],
    "content": [
        "Size%3A29gb",
    ],
    "cdn": {
        "_id": "68d2d19efa0b6f4bdf0713b9",
        "clear": "http%3A%2F%2Ffs2.inc-group.org",
        "onion": (
            "http%3A%2F%2Finc2eoul6blpkhj4lnxrwdcd3xwardnfk5a245bwrj7gx2gcbnxodwid.onion"
        ),
    },
    "leakAt": 1791028920000,
    "createdAt": 1790624216767,
}


def main():
    disclosure = parse_disclosure(
        SAMPLE_DISCLOSURE,
        announcement_id="6abab9929cd108bf261f2fdd",
    )

    print("=" * 80)
    print("PARSED DISCLOSURE")
    print("=" * 80)

    print(disclosure.model_dump_json(indent=2))

    assert disclosure.id == "6abac1d8366c46847ef8e876"
    assert disclosure.announcement_id == "6abab9929cd108bf261f2fdd"

    assert disclosure.title == "Disclosure of data :"

    assert "Financial data" in disclosure.categories
    assert "Customer's data" in disclosure.categories

    assert disclosure.content == ["Size:29gb"]
    assert disclosure.size == "29gb"

    assert disclosure.cdn_id == "68d2d19efa0b6f4bdf0713b9"

    assert (
        disclosure.cdn_onion
        == "http://inc2eoul6blpkhj4lnxrwdcd3xwardnfk5a245bwrj7gx2gcbnxodwid.onion"
    )

    assert disclosure.leak_at is not None
    assert disclosure.created_at is not None

    print()
    print("Disclosure parser test passed.")


if __name__ == "__main__":
    main()