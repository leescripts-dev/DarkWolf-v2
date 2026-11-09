from app.collectors.tor import TorClient
from app.core.config import settings


ANNOUNCEMENT_IDS = [
    "6abe94e19cd108bf26a37cde",
    "6abe3fe69cd108bf2698cf60",
    "6abe3c919cd108bf26987392",
]


def main():
    client = TorClient(timeout=30)

    for announcement_id in ANNOUNCEMENT_IDS:
        url = (
            f"{settings.inc_ransom_api_base_url}"
            f"/disclosures/{announcement_id}"
        )

        print("\n" + "=" * 80)
        print(f"Announcement ID: {announcement_id}")
        print(f"URL: {url}")

        try:
            response = client.get(url)

            print(f"Status: {response.status_code}")
            print(
                f"Content-Type: "
                f"{response.headers.get('content-type')}"
            )
            print(f"Size: {len(response.content)} bytes")

            print("\nResponse:")
            print(response.json())

        except Exception as exc:
            print(f"\nERROR: {type(exc).__name__}")
            print(exc)


if __name__ == "__main__":
    main()