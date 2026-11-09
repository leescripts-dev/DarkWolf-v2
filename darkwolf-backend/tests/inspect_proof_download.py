from app.collectors.tor import TorClient
from app.core.config import settings


def main():
    client = TorClient()

    proof_id = "6abe94e19cd108bf26a37cd3"

    url = (
        f"{settings.inc_ransom_url.rstrip('/')}"
        f"/api/v1/blog/download/{proof_id}"
    )

    print(f"URL: {url}")

    response = client.get(url)

    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    print(f"Content-Length: {response.headers.get('content-length')}")
    print(f"Final URL: {response.url}")

    print("\nHeaders:")
    for key, value in response.headers.items():
        print(f"{key}: {value}")

    print(f"\nResponse size: {len(response.content)} bytes")


if __name__ == "__main__":
    main()