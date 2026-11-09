from datetime import datetime, timezone

from app.entities.mapper import map_observation
from app.models.observation import Observation


def main():
    observation = Observation(
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

    result = map_observation(observation)

    print("\nORGANIZATION")
    print(result["organization"].model_dump())

    print("\nCOUNTRY")
    print(result["country"].model_dump())

    print("\nLEAK")
    print(result["leak"].model_dump())

    print("\nSOURCE")
    print(result["source"].model_dump())


if __name__ == "__main__":
    main()