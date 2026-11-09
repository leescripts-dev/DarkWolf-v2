from app.db.mongodb import db
from app.snapshots.disclosure_differ import compare_disclosures


events = db["events"]
disclosure_observations = db["disclosure_observations"]


def get_disclosure_observation(event: dict):
    details = event.get("details", {})

    disclosure_id = details.get("disclosure_id")
    announcement_id = details.get("announcement_id")

    if disclosure_id:
        observation = disclosure_observations.find_one(
            {
                "source": "inc_ransom",
                "disclosure_id": disclosure_id,
            }
        )

        if observation:
            return observation

    if announcement_id:
        observation = disclosure_observations.find_one(
            {
                "source": "inc_ransom",
                "announcement_id": announcement_id,
            }
        )

        if observation:
            return observation

    return None


def main():
    cursor = events.find(
        {
            "source": "inc_ransom",
            "event_type": "DISCLOSURE_DISCOVERED",
            "changes": {},
        }
    )

    processed = 0
    found = 0
    updated = 0
    not_found = 0

    print("\nDISCLOSURE CHANGE BACKFILL")
    print("=" * 70)

    for event in cursor:
        processed += 1

        observation = get_disclosure_observation(event)

        if not observation:
            not_found += 1

            print(
                f"\nEvent {event['_id']}: "
                "DISCLOSURE OBSERVATION NOT FOUND"
            )

            continue

        found += 1

        comparison = compare_disclosures(
            previous=None,
            current=observation,
        )

        changed_fields = comparison.get(
            "changed_fields",
            [],
        )

        changes = comparison.get(
            "changes",
            {},
        )

        print("\nEVENT")
        print("-" * 70)

        print(
            "Event ID:",
            event["_id"],
        )

        print(
            "Disclosure ID:",
            observation.get("disclosure_id"),
        )

        print(
            "Announcement ID:",
            observation.get("announcement_id"),
        )

        print("\nCHANGED FIELDS")
        print(changed_fields)

        print("\nCHANGES")

        for field, change in changes.items():
            print(f"\n{field}:")
            print(
                "  Previous:",
                change.get("previous"),
            )
            print(
                "  Current :",
                change.get("current"),
            )

        # -----------------------------------------------------
        # Update existing event
        # -----------------------------------------------------
        result = events.update_one(
            {
                "_id": event["_id"],
                "event_type": "DISCLOSURE_DISCOVERED",
                "changes": {},
            },
            {
                "$set": {
                    "changed_fields": changed_fields,
                    "changes": changes,
                }
            },
        )

        if result.modified_count == 1:
            updated += 1

            print("\nSTATUS: UPDATED")
        else:
            print("\nSTATUS: NOT UPDATED")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(
        "Events processed:",
        processed,
    )

    print(
        "Observations found:",
        found,
    )

    print(
        "Observations not found:",
        not_found,
    )

    print(
        "Events updated:",
        updated,
    )

    print(
        "Mode: WRITE"
    )

    print(
        "MongoDB was modified."
    )


if __name__ == "__main__":
    main()