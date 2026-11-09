from app.db.mongodb import db
from app.models.disclosure_observation import DisclosureObservation


collection = db["disclosure_observations"]


def save_disclosure_observation(
    observation: DisclosureObservation,
) -> str:
    result = collection.insert_one(
        observation.model_dump()
    )

    return str(result.inserted_id)


def get_latest_disclosure_observation(
    source: str,
    disclosure_id: str,
):
    return collection.find_one(
        {
            "source": source,
            "disclosure_id": disclosure_id,
        },
        sort=[("observed_at", -1)],
    )