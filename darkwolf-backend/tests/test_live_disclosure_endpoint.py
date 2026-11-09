from app.collectors.tor import TorClient
from app.core.config import settings


ANNOUNCEMENT_ID = "6abab9929cd108bf261f2fdd"


def main():
    client = TorClient()

    url = (
        f"{settings.inc_ransom_api_base_url}"
        f"/disclosures/{ANNOUNCEMENT_ID}"
    )

    print("\nREQUEST:")
    print(url)

    response = client.get(url)

    print("\nSTATUS:")
    print(response.status_code)

    data = response.json()

    print("\nPAYLOAD:")

    payload = data.get("payload", [])

    print(f"Disclosures returned: {len(payload)}")

    for disclosure in payload:
        print("\nDisclosure:")
        print(disclosure)


if __name__ == "__main__":
    main()