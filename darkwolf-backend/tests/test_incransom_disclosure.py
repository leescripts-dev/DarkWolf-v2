from app.collectors.tor import TorClient
from app.core.config import settings


client = TorClient()

disclosure_id = "6abe94e19cd108bf26a37cde"

url = (
    f"{settings.inc_ransom_api_base_url}"
    f"/announcement/{disclosure_id}"
)

response = client.get(url)

print("Status:", response.status_code)
print("Content-Type:", response.headers.get("content-type"))
print("Content-Length:", len(response.content))

print("\nResponse:\n")
print(response.text)