from app.collection.service import IncRansomCollectionService


def main():
    service = IncRansomCollectionService()

    result = service.collect_all_historical(
        per_page=15
    )

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()