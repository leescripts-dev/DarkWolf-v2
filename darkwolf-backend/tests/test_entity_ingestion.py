from app.entities.service import ingest_inc_ransom_entities


def main():
    result = ingest_inc_ransom_entities()

    print("\nENTITY INGESTION RESULT")
    print("=" * 50)

    print(
        "Source:",
        result["source"],
    )

    print(
        "Observations processed:",
        result["observations_processed"],
    )

    print(
        "Observations successful:",
        result["observations_successful"],
    )

    print(
        "Organizations:",
        result["organizations"],
    )

    print(
        "Countries:",
        result["countries"],
    )

    print(
        "Sources:",
        result["sources"],
    )

    print(
        "Leaks:",
        result["leaks"],
    )

    print(
        "Errors:",
        len(result["errors"]),
    )

    if result["errors"]:
        print("\nERROR DETAILS")

        for error in result["errors"]:
            print(error)


if __name__ == "__main__":
    main()