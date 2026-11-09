from app.collection.service import (
    IncRansomCollectionService,
)


ANNOUNCEMENT_ID = "6abab9929cd108bf261f2fdd"


def main():
    service = IncRansomCollectionService()

    result = service.collect_announcement(
        announcement_id=ANNOUNCEMENT_ID
    )

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()