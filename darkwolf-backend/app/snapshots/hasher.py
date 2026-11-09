import hashlib
import json


def build_content_payload(
    observation_data: dict,
) -> dict:

    return {
        "company_name": observation_data.get(
            "company_name"
        ),
        "company_id": observation_data.get(
            "company_id"
        ),
        "country": observation_data.get(
            "country"
        ),
        "revenue": observation_data.get(
            "revenue"
        ),
        "categories": sorted(
            observation_data.get(
                "categories",
                []
            )
        ),
        "descriptions": observation_data.get(
            "descriptions",
            []
        ),
        "proof_ids": sorted(
            observation_data.get(
                "proof_ids",
                []
            )
        ),
        "logo_id": observation_data.get(
            "logo_id"
        ),
        "leak_at": observation_data.get(
            "leak_at"
        ),
        "cdn": observation_data.get(
            "cdn"
        ),
    }


def calculate_content_hash(
    observation_data: dict,
) -> str:

    payload = build_content_payload(
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