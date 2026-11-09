from datetime import datetime, timezone

from app.db.mongodb import db
from app.entities.mapper import map_observation
from app.entities.repository import persist_mapped_entities
from app.models.observation import Observation


def build_test_observation():
    return Observation(
        source="inc_ransom",
        source_id="test-announcement-001",
        collection_run_id="test-run-001",
        raw_evidence_id=None,
        observed_at=datetime.now(timezone.utc),

        company_name="Example Corporation",
        company_id="company-123",

        country="Germany",
        revenue=28.9,

        categories=[
            "Financial data",
            "Confidential",
        ],

        descriptions=[
            "Example Corporation data disclosure."
        ],

        proof_ids=[
            "proof-001",
            "proof-002",
        ],

        logo_id=None,
        visits=10,

        leak_at=None,
        source_created_at=None,
        source_updated_at=None,

        cdn=None,

        content_hash="test-hash",
    )


def main():
    observation = build_test_observation()

    mapped = map_observation(observation)

    result = persist_mapped_entities(mapped)

    print("\nPERSISTED")
    print(result)

    print("\nCOUNTS")

    print(
        "Organizations:",
        db["organizations"].count_documents(
            {"id": "company-123"}
        ),
    )

    print(
        "Countries:",
        db["countries"].count_documents(
            {
                "normalized_name": "germany"
            }
        ),
    )

    print(
        "Sources:",
        db["sources"].count_documents(
            {
                "id": mapped["source"].id
            }
        ),
    )

    print(
        "Leaks:",
        db["leaks"].count_documents(
            {
                "id": mapped["leak"].id
            }
        ),
    )


if __name__ == "__main__":
    main()