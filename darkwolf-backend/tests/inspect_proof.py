from app.collectors.tor import TorClient
from app.core.config import settings


def main():
    client = TorClient()

    # Get the first announcement from the live API
    listing_url = (
        f"{settings.inc_ransom_api_base_url}"
        f"/announcements?page=1&perPage=1"
    )

    listing_response = client.get(listing_url)
    listing_data = listing_response.json()

    announcements = (
        listing_data
        .get("payload", {})
        .get("announcements", [])
    )

    if not announcements:
        print("No announcements found.")
        return

    announcement_id = announcements[0].get("_id")

    print(f"Announcement ID: {announcement_id}")

    # Get the full announcement
    detail_url = (
        f"{settings.inc_ransom_api_base_url}"
        f"/announcement/{announcement_id}"
    )

    detail_response = client.get(detail_url)
    detail_data = detail_response.json()

    detail = detail_data.get("payload")

    if not detail:
        print("No detail payload found.")
        return

    print("\nPROOF:")
    print("-" * 50)

    proof = detail.get("proof", [])

    print(f"Type: {type(proof).__name__}")
    print(f"Count: {len(proof)}")

    for index, item in enumerate(proof):
        print(f"\n[{index}]")
        print(repr(item))


if __name__ == "__main__":
    main()