import hashlib
import json


def calculate_response_hash(
    response_body: dict,
) -> str:

    serialized = json.dumps(
        response_body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()