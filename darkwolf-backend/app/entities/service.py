from app.db.mongodb import db
from app.entities.mapper import map_observation
from app.entities.repository import persist_mapped_entities


observations = db["observations"]


def ingest_inc_ransom_entities() -> dict:
    """
    Build canonical entities from all Inc Ransom observations.

    Observations are read-only. This process only creates/updates
    canonical entity collections.
    """

    query = {
        "source": "inc_ransom",
    }

    cursor = observations.find(query).sort(
        "observed_at",
        1,
    )

    processed = 0
    successful = 0
    errors = []

    organization_ids = set()
    country_ids = set()
    source_ids = set()
    leak_ids = set()

    for observation_document in cursor:
        processed += 1

        try:
            observation = observation_document

            # Convert MongoDB document into the Pydantic model.
            # MongoDB's internal _id is not part of the Observation model.
            observation.pop("_id", None)

            from app.models.observation import Observation

            observation_model = Observation.model_validate(
                observation
            )

            mapped = map_observation(
                observation_model
            )

            result = persist_mapped_entities(
                mapped
            )

            successful += 1

            organization_ids.add(
                result["organization_id"]
            )

            if result["country_id"]:
                country_ids.add(
                    result["country_id"]
                )

            source_ids.add(
                result["source_id"]
            )

            leak_ids.add(
                result["leak_id"]
            )

        except Exception as exc:
            errors.append(
                {
                    "observation_id": str(
                        observation_document.get("_id")
                    ),
                    "source_id": observation_document.get(
                        "source_id"
                    ),
                    "error": str(exc),
                }
            )

    return {
        "source": "inc_ransom",
        "observations_processed": processed,
        "observations_successful": successful,
        "organizations": len(organization_ids),
        "countries": len(country_ids),
        "sources": len(source_ids),
        "leaks": len(leak_ids),
        "errors": errors,
    }