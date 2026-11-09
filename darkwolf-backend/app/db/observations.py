from app.db.mongodb import db
from app.models.observation import Observation


collection = db["observations"]


def save_observation(observation: Observation) -> str:
    result = collection.insert_one(
        observation.model_dump()
    )

    return str(result.inserted_id)


def get_latest_observation(
    source: str,
    source_id: str,
):
    return collection.find_one(
        {
            "source": source,
            "source_id": source_id,
        },
        sort=[
            ("observed_at", -1),
        ],
    )