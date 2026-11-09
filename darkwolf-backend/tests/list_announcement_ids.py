from app.sites.inc_ransom.collector import IncRansomCollector


def main():
    collector = IncRansomCollector()

    response = collector.get_announcements_page(
        page=1,
        per_page=3,
    )

    data = response.json()

    announcements = (
        data
        .get("payload", {})
        .get("announcements", [])
    )

    print(f"Found {len(announcements)} announcements\n")

    for index, announcement in enumerate(announcements, start=1):
        print(f"{index}. ID: {announcement.get('_id')}")
        print(
            f"   Company: "
            f"{announcement.get('company', {}).get('company_name')}"
        )


if __name__ == "__main__":
    main()