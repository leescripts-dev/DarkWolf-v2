from app.collectors.tor import TorClient
from app.core.config import settings


def main():
    client = TorClient()

    base_url = settings.inc_ransom_url.rstrip("/")
    js_url = f"{base_url}/assets/index-DjzwPXL3.js"

    response = client.get(js_url)

    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    print(f"Length: {len(response.text)}")

    # Save locally so we can inspect it
    output_file = "tests/inc_ransom_frontend.js"

    with open(output_file, "w", encoding="utf-8") as file:
        file.write(response.text)

    print(f"\nSaved to: {output_file}")


if __name__ == "__main__":
    main()