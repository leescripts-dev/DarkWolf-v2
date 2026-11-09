from app.collectors.tor import TorClient
from app.core.config import settings
from app.snapshots.evidence import (
    build_raw_evidence,
)


client = TorClient()

announcement_id = (
    "6abe94e19cd108bf26a37cde"
)

endpoint = (
    f"{settings.inc_ransom_api_base_url}"
    f"/announcement/{announcement_id}"
)

response = client.get(endpoint)

evidence = build_raw_evidence(
    source="inc_ransom",
    source_id=announcement_id,
    endpoint=endpoint,
    response=response,
)

print("\n" + "=" * 60)

print(
    "Source:",
    evidence.source,
)

print(
    "Source ID:",
    evidence.source_id,
)

print(
    "Status:",
    evidence.status_code,
)

print(
    "Content Type:",
    evidence.content_type,
)

print(
    "Captured At:",
    evidence.captured_at,
)

print(
    "Response Hash:",
    evidence.response_hash,
)

print(
    "Response Keys:",
    list(
        evidence.response_body.keys()
    ),
)