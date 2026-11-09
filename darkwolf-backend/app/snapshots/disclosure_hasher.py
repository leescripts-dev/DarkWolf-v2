import hashlib
import json


def build_disclosure_content_payload(
    observation_data: dict,
) -> dict:
    return {
        "title": observation_data.get("title"),
        "categories": sorted(
            observation_data.get("categories", [])
        ),
        "content": observation_data.get("content", []),
        "size": observation_data.get("size"),
        "leak_at": observation_data.get("leak_at"),
        "cdn_id": observation_data.get("cdn_id"),
        "cdn_onion": observation_data.get("cdn_onion"),
        "cdn_clear": observation_data.get("cdn_clear"),
    }


def calculate_disclosure_content_hash(
    observation_data: dict,
) -> str:
    payload = build_disclosure_content_payload(
        observation_data
    )

    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()