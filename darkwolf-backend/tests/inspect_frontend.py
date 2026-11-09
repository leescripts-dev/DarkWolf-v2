from app.collectors.tor import TorClient
from app.core.config import settings


def main():
    client = TorClient()

    response = client.get(settings.inc_ransom_url)

    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    print(f"Length: {len(response.text)}")

    print("\nHTML:")
    print(response.text[:5000])


if __name__ == "__main__":
    main()