from app.collectors.tor import TorClient


DISCLOSURE_ID = "6abac1d8366c46847ef8e876"

CDN_ONION = (
    "http://inc2eoul6blpkhj4lnxrwdcd3xwardnfk5a245bwrj7gx2gcbnxodwid.onion"
)


def main():
    client = TorClient(timeout=60)

    url = f"{CDN_ONION}/api/v1/blog/get/folder"

    payload = {
        "disclosureId": DISCLOSURE_ID,
        "path": "./",
    }

    print("=" * 80)
    print("DISCLOSURE FILE TREE")
    print("=" * 80)

    print(f"URL: {url}")
    print(f"Disclosure ID: {DISCLOSURE_ID}")
    print(f"Path: {payload['path']}")
    print()

    try:
        response = client.post(
            url,
            json=payload,
        )

        print(f"Status: {response.status_code}")
        print(
            f"Content-Type: "
            f"{response.headers.get('content-type')}"
        )
        print(f"Size: {len(response.content)} bytes")
        print()

        print("Response:")
        print(response.json())

    except Exception as exc:
        print()
        print(f"ERROR: {type(exc).__name__}")
        print(exc)


if __name__ == "__main__":
    main()