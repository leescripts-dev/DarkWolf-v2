from app.sites.inc_ransom.disclosure_models import (
    IncRansomDisclosure,
)
from app.snapshots.disclosure_manager import (
    build_disclosure_observation,
)


def main():
    disclosure = IncRansomDisclosure(
        id="disclosure-001",
        announcement_id="announcement-001",

        title="Disclosure of data :",

        categories=[
            "Contracts",
            "Confidential",
            "Financial data",
        ],

        content=[
            "Size:29gb",
        ],

        size="29gb",

        cdn_id="cdn-001",
        cdn_onion="http://example.onion",
        cdn_clear="http://example.org",
    )

    observation = build_disclosure_observation(
        disclosure=disclosure,
        collection_run_id="run-001",
    )

    print("=" * 80)
    print("DISCLOSURE OBSERVATION")
    print("=" * 80)
    print(observation.model_dump_json(indent=2))

    assert observation.source == "inc_ransom"
    assert observation.disclosure_id == "disclosure-001"
    assert observation.announcement_id == "announcement-001"

    assert observation.title == "Disclosure of data :"
    assert observation.size == "29gb"

    assert observation.categories == [
        "Contracts",
        "Confidential",
        "Financial data",
    ]

    assert observation.content == ["Size:29gb"]

    assert observation.content_hash
    assert len(observation.content_hash) == 64

    print()
    print("Disclosure observation test passed.")


if __name__ == "__main__":
    main()