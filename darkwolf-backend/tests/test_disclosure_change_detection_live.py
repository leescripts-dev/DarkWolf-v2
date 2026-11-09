from app.db.mongodb import db
from app.events.disclosure_detector import detect_disclosure_events
from app.snapshots.disclosure_differ import compare_disclosures
from app.snapshots.disclosure_hasher import (
    calculate_disclosure_content_hash,
)


def main():
    collection = db["disclosure_observations"]

    latest = collection.find_one(
        {"source": "inc_ransom"},
        sort=[("observed_at", -1)],
    )

    if not latest:
        raise RuntimeError(
            "No Inc Ransom disclosure observations found"
        )

    disclosure_id = latest["disclosure_id"]

    # Copy the observation.
    current = dict(latest)

    print("\nDISCLOSURE ID:")
    print(disclosure_id)

    print("\nORIGINAL SIZE:")
    print(latest.get("size"))

    # Simulate a real metadata change.
    current["size"] = "35gb"

    # Recalculate the content hash after the change.
    current["content_hash"] = (
        calculate_disclosure_content_hash(current)
    )

    comparison = compare_disclosures(
        previous=latest,
        current=current,
    )

    print("\nSIMULATED SIZE:")
    print(current.get("size"))

    print("\nCOMPARISON:")
    print(comparison)

    events = detect_disclosure_events(
        comparison
    )

    print("\nEVENTS:")

    if not events:
        print("No events generated.")
        return

    for event in events:
        print(event)


if __name__ == "__main__":
    main()