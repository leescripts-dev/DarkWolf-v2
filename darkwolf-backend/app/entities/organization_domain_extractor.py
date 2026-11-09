import re
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.entities.domain_validator import validate_domain


DOMAIN_PATTERN = re.compile(
    r"""
    (?:
        https?://
        |
        www\.
    )?
    \b
    (?:[a-zA-Z0-9-]+\.)+
    [a-zA-Z]{2,}
    \b
    """,
    re.VERBOSE,
)


class OrganizationDomainFinding(BaseModel):
    source: str
    source_id: str
    organization_name: str
    domains: list[str] = Field(default_factory=list)
    evidence_type: str
    observed_at: datetime | None = None


def normalize_domain(value: str) -> str:
    """
    Normalize a domain-like value.

    Examples:
        https://www.example.com/path -> example.com
        www.example.com              -> example.com
        Example.COM                  -> example.com
        bcch.local                   -> bcch.local
    """
    value = value.strip().lower()

    if "://" in value:
        parsed = urlparse(value)
        value = parsed.netloc

    value = value.split("/")[0]
    value = value.split(":")[0]

    if value.startswith("www."):
        value = value[4:]

    return value.strip(".")


def extract_domains(text: str | None) -> list[str]:
    """
    Extract domain-like candidates from text.

    This function performs extraction and normalization only.
    Validation is performed separately after extraction.
    """
    if not text:
        return []

    matches = DOMAIN_PATTERN.findall(text)

    domains = {
        normalize_domain(match)
        for match in matches
    }

    return sorted(
        domain
        for domain in domains
        if domain
    )


def validate_extracted_domains(domains: list[str]) -> list[str]:
    """
    Validate extracted domain candidates.

    Only domains accepted by the domain validator are returned.
    Internal hostnames such as *.local are retained when supported
    by the validator.
    """
    validated_domains = []

    for domain in domains:
        result = validate_domain(domain)

        if result.valid:
            validated_domains.append(result.domain)

    return sorted(set(validated_domains))


def extract_organization_domains(
    organization_name: str | None,
    text: str | None,
) -> tuple[str, list[str]]:
    """
    Extract an organization name and associated domain candidates.

    Domains are extracted from:
        1. The structured organization/company name.
        2. The observation description/free text.

    The organization name itself is preserved exactly as supplied
    by the source.

    If no organization name exists but a domain is found, the first
    normalized domain is used as a temporary organization identifier.

    If neither exists:
        organization = "N/A"
        domains = []
    """
    domains: set[str] = set()

    # Extract domains directly from the organization name.
    domains.update(
        extract_domains(organization_name)
    )

    # Extract domains from descriptions/free text.
    domains.update(
        extract_domains(text)
    )

    # Validate all extracted candidates.
    normalized_domains = validate_extracted_domains(
        sorted(domains)
    )

    # Preserve the original organization name.
    if organization_name and organization_name.strip():
        return (
            organization_name.strip(),
            normalized_domains,
        )

    # If there is no organization name but a valid domain exists,
    # use the first domain as a deterministic fallback.
    if normalized_domains:
        return (
            normalized_domains[0],
            normalized_domains,
        )

    return (
        "N/A",
        [],
    )


def build_finding(
    *,
    source: str,
    source_id: str,
    organization_name: str | None,
    text: str | None,
    evidence_type: str,
    observed_at: datetime | None = None,
) -> OrganizationDomainFinding:
    """
    Build an organization/domain extraction finding.
    """
    organization, domains = extract_organization_domains(
        organization_name=organization_name,
        text=text,
    )

    return OrganizationDomainFinding(
        source=source,
        source_id=source_id,
        organization_name=organization,
        domains=domains,
        evidence_type=evidence_type,
        observed_at=observed_at,
    )