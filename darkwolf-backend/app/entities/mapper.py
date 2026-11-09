from datetime import datetime, timezone
import hashlib

from app.entities.models import (
    Country,
    Domain,
    Leak,
    Organization,
    Source,
)
from app.models.observation import Observation


SOURCE_NAME = "inc_ransom"
SOURCE_DISPLAY_NAME = "Inc Ransom"


def build_entity_id(entity_type: str, value: str) -> str:
    """
    Generate a deterministic ID for a canonical entity.

    The same source/value combination always produces
    the same entity ID.
    """
    normalized = value.strip().lower()

    raw = f"{entity_type}:{normalized}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def normalize_country(value: str | None) -> str | None:
    if not value:
        return None

    return " ".join(value.strip().split()).lower()


def map_country(
    country_name: str | None,
    source: str = SOURCE_NAME,
) -> Country | None:
    if not country_name:
        return None

    normalized = normalize_country(country_name)

    if not normalized:
        return None

    return Country(
        id=build_entity_id("country", normalized),
        name=country_name.strip(),
        normalized_name=normalized,
        source=source,
    )


def map_organization(
    observation: Observation,
) -> Organization:
    source_name = observation.source
    organization_id = (
        observation.company_id
        or build_entity_id(
            "organization",
            f"{source_name}:{observation.company_name}",
        )
    )

    return Organization(
        id=organization_id,
        name=observation.company_name,
        source=source_name,
        source_ids={
            source_name: organization_id,
        },
        country_id=(
            build_entity_id(
                "country",
                normalize_country(observation.country),
            )
            if observation.country
            else None
        ),
        revenue=observation.revenue,
        first_seen=observation.observed_at,
        last_seen=observation.observed_at,
    )


def map_leak(
    observation: Observation,
    organization: Organization,
) -> Leak:
    return Leak(
        id=build_entity_id(
            "leak",
            f"{observation.source}:{observation.source_id}",
        ),
        source=observation.source,
        source_id=observation.source_id,
        organization_id=organization.id,
        categories=observation.categories,
        proof_ids=observation.proof_ids,
        leak_at=observation.leak_at,
        first_seen=observation.observed_at,
        last_seen=observation.observed_at,
    )


def map_domain(
    observation: Observation,
    organization: Organization,
) -> Domain | None:
    value = observation.domain
    if not value:
        return None

    domain = value.casefold().strip().removeprefix("www.").strip(".")
    if not domain:
        return None
    return Domain(
        id=build_entity_id("domain", domain),
        domain=domain,
        normalized_domain=domain,
        organization_id=organization.id,
        first_seen=observation.observed_at,
        last_seen=observation.observed_at,
    )


def map_source() -> Source:
    return Source(
        id=build_entity_id(
            "source",
            SOURCE_NAME,
        ),
        name=SOURCE_DISPLAY_NAME,
        source_type="ransomware_leak_site",
        ransomware_group="Inc",
    )


def map_observation(
    observation: Observation,
) -> dict:
    """
    Convert one Inc Ransom observation into
    canonical entities.
    """

    organization = map_organization(observation)

    country = map_country(
        observation.country,
        source=observation.source,
    )

    leak = map_leak(
        observation,
        organization,
    )

    source_name = observation.source_display_name
    ransomware_group = observation.ransomware_group
    source_url = observation.source_url
    if observation.source == SOURCE_NAME:
        source_name = source_name or SOURCE_DISPLAY_NAME
        ransomware_group = ransomware_group or "Inc"

    source = Source(
        id=build_entity_id("source", observation.source),
        name=source_name or observation.source,
        source_type="ransomware_leak_site",
        ransomware_group=ransomware_group,
        url=source_url,
    )

    return {
        "organization": organization,
        "domain": map_domain(observation, organization),
        "country": country,
        "leak": leak,
        "source": source,
    }
