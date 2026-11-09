from uuid import uuid4

from app.collectors.tor import TorClient
from app.core.config import settings
from app.db.disclosure_observations import (
    get_latest_disclosure_observation,
    save_disclosure_observation,
)
from app.db.raw_evidence import save_raw_evidence
from app.events.disclosure_detector import detect_disclosure_events
from app.models.disclosure_observation import DisclosureObservation
from app.sites.inc_ransom.disclosure_parser import parse_disclosure
from app.snapshots.disclosure_differ import compare_disclosures
from app.snapshots.disclosure_manager import (
    build_disclosure_observation,
)
from app.snapshots.evidence import build_raw_evidence


ANNOUNCEMENT_ID = "6abab9929cd108bf261f2fdd"


def main():
    collection_run_id = str(uuid4())

    client = TorClient()

    url = (
        f"{settings.inc_ransom_api_base_url}"
        f"/disclosures/{ANNOUNCEMENT_ID}"
    )

    print("\nREQUEST:")
    print(url)

    response = client.get(url)

    print("\nSTATUS:")
    print(response.status_code)

    # Store the real API response as raw evidence.
    evidence = build_raw_evidence(
        source="inc_ransom",
        source_id=ANNOUNCEMENT_ID,
        collection_run_id=collection_run_id,
        endpoint=str(response.url),
        response=response,
        metadata={
            "type": "disclosure",
            "announcement_id": ANNOUNCEMENT_ID,
        },
    )

    raw_evidence_id = save_raw_evidence(evidence)

    data = response.json()

    disclosures = data.get("payload", [])

    print("\nDISCLOSURES FOUND:")
    print(len(disclosures))

    for disclosure_data in disclosures:

        disclosure = parse_disclosure(
            disclosure_data,
            announcement_id=ANNOUNCEMENT_ID,
        )

        observation = build_disclosure_observation(
            disclosure=disclosure,
            collection_run_id=collection_run_id,
            raw_evidence_id=raw_evidence_id,
        )

        previous = get_latest_disclosure_observation(
            source="inc_ransom",
            disclosure_id=disclosure.id,
        )

        comparison = compare_disclosures(
            previous=previous,
            current=observation.model_dump(),
        )

        print("\nDISCLOSURE ID:")
        print(disclosure.id)

        print("\nTITLE:")
        print(disclosure.title)

        print("\nSIZE:")
        print(disclosure.size)

        print("\nCOMPARISON:")
        print(comparison)

        # Save the real observation.
        observation_id = save_disclosure_observation(
            observation
        )

        print("\nOBSERVATION SAVED:")
        print(observation_id)

        events = detect_disclosure_events(
            comparison
        )

        print("\nEVENTS:")

        if not events:
            print("No events generated.")
        else:
            for event in events:
                print(event)


if __name__ == "__main__":
    main()