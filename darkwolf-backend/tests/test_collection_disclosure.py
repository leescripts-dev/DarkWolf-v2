from app.collection.service import (
    IncRansomCollectionService,
)


ANNOUNCEMENT_ID = "6abab9929cd108bf261f2fdd"


def main():
    service = IncRansomCollectionService()

    # Directly exercise the live announcement through the
    # same collection service used by the normal collector.
    result = service.collect_page(
        page=1,
        per_page=15,
    )

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()