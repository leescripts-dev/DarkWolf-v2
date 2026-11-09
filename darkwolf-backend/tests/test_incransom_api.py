from app.collectors.tor import TorClient
from app.core.config import settings


client = TorClient()

url = f"{settings.inc_ransom_api_base_url}/announcements"

response = client.get(
    f"{url}?page=1&perPage=15"
)

print("Status:", response.status_code)
print("Content-Type:", response.headers.get("content-type"))
print("Content-Length:", len(response.content))

print("\nResponse:\n")
print(response.text)