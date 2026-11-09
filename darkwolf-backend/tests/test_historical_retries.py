from app.collection.service import (
    IncRansomCollectionService,
)


FAILED_IDS = [
    "69fcf1d98f1d14b743b95793",
    "6878deebc7b82dfe0b26c9bf",
    "6881498bc7b82dfe0bd06d92",
    "67f7038c516e69ca6178b3ed",
    "666b00f33547f22b7c4b98f1",
    "6627388cff06b807bef8dfdf",
]


def main():
    service = IncRansomCollectionService()

    for announcement_id in FAILED_IDS:
        print(
            f"\nProcessing {announcement_id}"
        )

        try:
            result = (
                service.collect_historical_announcement(
                    announcement_id
                )
            )

            print(result)

        except Exception as exc:
            print(
                f"FAILED: {announcement_id}"
            )
            print(exc)


if __name__ == "__main__":
    main()