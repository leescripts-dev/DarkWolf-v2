from app.collectors.tor import TorClient
from app.core.config import settings


def main():
    client = TorClient()

    announcement_id = "6abe94e19cd108bf26a37cde"

    url = (
        f"{settings.inc_ransom_api_base_url}"
        f"/disclosures/{announcement_id}"
    )

    print(f"URL: {url}")

    response = client.get(url)

    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    print("\nResponse:")
    print(response.json())


if __name__ == "__main__":
    main()