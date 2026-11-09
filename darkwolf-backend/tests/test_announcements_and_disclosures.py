from app.collectors.tor import TorClient
from app.core.config import settings


def main():
    client = TorClient(timeout=30)

    announcements_url = (
        f"{settings.inc_ransom_api_base_url}"
        "/announcements?page=1&perPage=15"
    )

    print("=" * 80)
    print("ANNOUNCEMENTS")
    print("=" * 80)

    response = client.get(announcements_url)

    print(f"Status: {response.status_code}")

    data = response.json()

    print(f"Type: {data.get('type')}")
    print(f"Message: {data.get('message')}")

    payload = data.get("payload", {})
    announcements = payload.get("announcements", [])

    print(f"Count: {len(announcements)}")
    print()

    for announcement in announcements:
        announcement_id = announcement.get("_id")
        company = announcement.get("company", {})

        print(f"ID: {announcement_id}")
        print(f"Company: {company.get('company_name')}")
        print(f"CDN: {announcement.get('cdn')}")
        print("-" * 80)

    print()
    print("=" * 80)
    print("DISCLOSURES")
    print("=" * 80)

    for announcement in announcements:
        announcement_id = announcement.get("_id")

        if not announcement_id:
            continue

        url = (
            f"{settings.inc_ransom_api_base_url}"
            f"/disclosures/{announcement_id}"
        )

        try:
            disclosure_response = client.get(url)
            disclosure_data = disclosure_response.json()

            print()
            print(f"ID: {announcement_id}")
            print(f"Status: {disclosure_response.status_code}")
            print(f"Response: {disclosure_data}")

        except Exception as exc:
            print()
            print(f"ID: {announcement_id}")
            print(f"ERROR: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()