from app.db.mongodb import db


def main():
    collection = db["disclosure_observations"]

    count = collection.count_documents(
        {"source": "inc_ransom"}
    )

    print(f"Disclosure observations: {count}")

    if count == 0:
        print("No disclosure observations exist.")
        return

    for document in collection.find(
        {"source": "inc_ransom"}
    ).sort("observed_at", -1).limit(5):

        print("\nDisclosure ID:")
        print(document.get("disclosure_id"))

        print("Announcement ID:")
        print(document.get("announcement_id"))

        print("Title:")
        print(document.get("title"))

        print("Size:")
        print(document.get("size"))

        print("Observed at:")
        print(document.get("observed_at"))


if __name__ == "__main__":
    main()