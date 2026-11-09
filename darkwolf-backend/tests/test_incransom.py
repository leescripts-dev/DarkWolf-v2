from app.collectors.tor import TorClient
from app.core.config import settings


client = TorClient()

response = client.get(settings.inc_ransom_url)

print("Status:", response.status_code)
print("Content-Type:", response.headers.get("content-type"))
print("Content-Length:", len(response.content))

print("\nFirst 500 characters:\n")
print(response.text[:500])