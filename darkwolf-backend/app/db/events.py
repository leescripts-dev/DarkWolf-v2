from app.db.mongodb import db
from app.models.event import ThreatEvent


collection = db["events"]


def save_event(event: ThreatEvent) -> str:
    result = collection.insert_one(
        event.model_dump()
    )

    return str(result.inserted_id)