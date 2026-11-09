from app.db.mongodb import db
from app.events.detector import detect_events
from app.snapshots.differ import compare_observations
from app.snapshots.hasher import calculate_content_hash


def main():
    collection = db["observations"]

    latest = collection.find_one(
        {"source": "inc_ransom"},
        sort=[("observed_at", -1)],
    )

    if not latest:
        raise RuntimeError(
            "No Inc Ransom observations found"
        )

    source_id = latest["source_id"]

    # Copy the latest observation so MongoDB is not modified.
    current = dict(latest)

    # Simulate a change.
    current["company_name"] = "DarkWolf_Test_Company"

    # Recalculate the hash after changing the field.
    current["content_hash"] = calculate_content_hash(
        current
    )

    comparison = compare_observations(
        previous=latest,
        current=current,
    )

    print("\nSOURCE ID:")
    print(source_id)

    print("\nCOMPARISON:")
    print(comparison)

    events = detect_events(comparison)

    print("\nEVENTS:")

    if not events:
        print("No events generated.")
        return

    for event in events:
        print(event)


if __name__ == "__main__":
    main()