from app.db.mongodb import db
from app.entities.models import (
    Country,
    Domain,
    Leak,
    Organization,
    Source,
)


organizations = db["organizations"]
countries = db["countries"]
industries = db["industries"]
domains = db["domains"]
threat_actors = db["threat_actors"]
leaks = db["leaks"]
sources = db["sources"]


def upsert_organization(
    organization: Organization,
) -> str:
    result = organizations.update_one(
        {"id": organization.id},
        {
            "$set": {
                "name": organization.name,
                "source": organization.source,
                "source_ids": organization.source_ids,
                "country_id": organization.country_id,
                "revenue": organization.revenue,
                "last_seen": organization.last_seen,
            },
            "$setOnInsert": {
                "first_seen": organization.first_seen,
            },
        },
        upsert=True,
    )

    return organization.id


def upsert_country(
    country: Country,
) -> str:
    countries.update_one(
        {"id": country.id},
        {
            "$set": {
                "name": country.name,
                "normalized_name": country.normalized_name,
                "source": country.source,
            }
        },
        upsert=True,
    )

    return country.id


def upsert_domain(
    domain: Domain,
) -> str:
    domains.update_one(
        {"id": domain.id},
        {
            "$set": {
                "domain": domain.domain,
                "normalized_domain": domain.normalized_domain,
                "organization_id": domain.organization_id,
                "last_seen": domain.last_seen,
            },
            "$setOnInsert": {
                "first_seen": domain.first_seen,
            },
        },
        upsert=True,
    )

    return domain.id


def upsert_source(
    source: Source,
) -> str:
    sources.update_one(
        {"id": source.id},
        {
            "$set": {
                "name": source.name,
                "source_type": source.source_type,
                "ransomware_group": source.ransomware_group,
                "url": source.url,
            }
        },
        upsert=True,
    )

    return source.id


def upsert_leak(
    leak: Leak,
) -> str:
    leaks.update_one(
        {"id": leak.id},
        {
            "$set": {
                "source": leak.source,
                "source_id": leak.source_id,
                "organization_id": leak.organization_id,
                "categories": leak.categories,
                "proof_ids": leak.proof_ids,
                "leak_at": leak.leak_at,
                "last_seen": leak.last_seen,
            },
            "$setOnInsert": {
                "first_seen": leak.first_seen,
            },
        },
        upsert=True,
    )

    return leak.id


def persist_mapped_entities(
    mapped: dict,
) -> dict:
    organization = mapped["organization"]
    domain = mapped.get("domain")
    country = mapped["country"]
    leak = mapped["leak"]
    source = mapped["source"]

    organization_id = upsert_organization(
        organization
    )

    domain_id = upsert_domain(domain) if domain else None

    country_id = None

    if country:
        country_id = upsert_country(country)

    source_id = upsert_source(source)

    leak_id = upsert_leak(leak)

    return {
        "organization_id": organization_id,
        "domain_id": domain_id,
        "country_id": country_id,
        "source_id": source_id,
        "leak_id": leak_id,
    }
