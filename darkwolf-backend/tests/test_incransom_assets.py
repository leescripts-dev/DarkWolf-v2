from urllib.parse import urljoin

from app.collectors.tor import TorClient
from app.core.config import settings


client = TorClient()

response = client.get(settings.inc_ransom_url)

print("Main page:", response.status_code)

html = response.text

script_path = "/assets/index-DjzwPXL3.js"
script_url = urljoin(settings.inc_ransom_url, script_path)

print("Fetching:", script_url)

script_response = client.get(script_url)

print("Script status:", script_response.status_code)
print("Script size:", len(script_response.content))

with open("tests/incransom_bundle.js", "w", encoding="utf-8") as file:
    file.write(script_response.text)

print("Saved: tests/incransom_bundle.js")