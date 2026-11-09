from app.collectors.tor import TorClient


CDN_ONION = (
    "http://inc2eoul6blpkhj4lnxrwdcd3xwardnfk5a245bwrj7gx2gcbnxodwid.onion"
)


def main():
    client = TorClient(timeout=30)

    print("=" * 80)
    print("CDN CONNECTION TEST")
    print("=" * 80)

    print(f"URL: {CDN_ONION}")

    try:
        response = client.get(CDN_ONION)

        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"Size: {len(response.content)} bytes")
        print()
        print(response.text[:1000])

    except Exception as exc:
        print()
        print(f"ERROR: {type(exc).__name__}")
        print(exc)


if __name__ == "__main__":
    main()