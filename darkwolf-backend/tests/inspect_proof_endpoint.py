from app.collectors.tor import TorClient
from app.core.config import settings


def main():
    client = TorClient()

    proof_id = "6abe94e19cd108bf26a37cd3"

    base = settings.inc_ransom_api_base_url

    candidates = [
        f"{base}/proof/{proof_id}",
        f"{base}/proofs/{proof_id}",
        f"{base}/file/{proof_id}",
        f"{base}/files/{proof_id}",
        f"{base}/download/{proof_id}",
    ]

    for url in candidates:
        print(f"\nTrying: {url}")

        try:
            response = client.get(url)

            print(f"Status: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type')}")
            print(f"Content-Length: {response.headers.get('content-length')}")

            try:
                print("JSON:")
                print(response.json())
            except Exception:
                print("Response is not JSON.")
                print("First 500 bytes:")
                print(response.content[:500])

        except Exception as exc:
            print(f"ERROR: {exc}")


if __name__ == "__main__":
    main()