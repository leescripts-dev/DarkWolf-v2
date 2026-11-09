from app.db.mongodb import db
from app.models.raw_evidence import RawEvidence


collection = db["raw_evidence"]


def save_raw_evidence(
    evidence: RawEvidence,
) -> str:

    result = collection.insert_one(
        evidence.model_dump()
    )

    return str(result.inserted_id)