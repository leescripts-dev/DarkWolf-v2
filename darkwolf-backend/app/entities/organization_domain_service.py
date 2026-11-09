from app.db.mongodb import db
from app.entities.models import Domain
from app.entities.organization_domain_extractor import build_finding
from app.entities.repository import upsert_domain
from app.entities.mapper import build_entity_id
from app.models.observation import Observation


observations = db["observations"]


def extract_inc_ransom_organization_domains() -> dict:
    cursor = observations.find(
        {"source": "inc_ransom"}
    )

    observations_processed = 0
    findings = []

    organizations_found = set()
    domains_found = set()

    for document in cursor:
        observations_processed += 1

        document.pop("_id", None)

        observation = Observation.model_validate(document)

        text = "\n".join(
            part
            for part in observation.descriptions
            if part
        )

        finding = build_finding(
            source=observation.source,
            source_id=observation.source_id,
            organization_name=observation.company_name,
            text=text,
            evidence_type="observation",
            observed_at=observation.observed_at,
        )

        findings.append(finding)

        organizations_found.add(
            finding.organization_name
        )

        for domain in finding.domains:
            domains_found.add(domain)

            normalized_domain = domain.strip().lower()

            domain_entity = Domain(
                id=build_entity_id(
                    "domain",
                    normalized_domain,
                ),
                domain=domain,
                normalized_domain=normalized_domain,
                organization_id=observation.company_id,
                first_seen=observation.observed_at,
                last_seen=observation.observed_at,
            )

            upsert_domain(domain_entity)

    return {
        "observations_processed": observations_processed,
        "findings": findings,
        "organizations_found": len(organizations_found),
        "domains_found": len(domains_found),
        "organizations": sorted(organizations_found),
        "domains": sorted(domains_found),
    }