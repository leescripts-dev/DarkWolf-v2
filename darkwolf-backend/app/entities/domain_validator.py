from enum import Enum
import re


class DomainType(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    INVALID = "invalid"


class DomainValidationResult:
    def __init__(
        self,
        domain: str,
        domain_type: DomainType,
        valid: bool,
        reason: str,
    ):
        self.domain = domain
        self.domain_type = domain_type
        self.valid = valid
        self.reason = reason


INTERNAL_SUFFIXES = {
    ".local",
    ".internal",
    ".localhost",
    ".lan",
    ".home",
    ".corp",
}


DOMAIN_LABEL_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def validate_domain(domain: str) -> DomainValidationResult:
    domain = domain.strip().lower().rstrip(".")

    if not domain:
        return DomainValidationResult(
            domain=domain,
            domain_type=DomainType.INVALID,
            valid=False,
            reason="empty_domain",
        )

    # Internal hostnames
    for suffix in INTERNAL_SUFFIXES:
        if domain.endswith(suffix):
            return DomainValidationResult(
                domain=domain,
                domain_type=DomainType.INTERNAL,
                valid=True,
                reason="internal_hostname",
            )

    parts = domain.split(".")

    # A public domain must contain at least:
    # domain.tld
    if len(parts) < 2:
        return DomainValidationResult(
            domain=domain,
            domain_type=DomainType.INVALID,
            valid=False,
            reason="missing_tld",
        )

    # Validate individual labels
    for label in parts:
        if not DOMAIN_LABEL_PATTERN.fullmatch(label):
            return DomainValidationResult(
                domain=domain,
                domain_type=DomainType.INVALID,
                valid=False,
                reason="invalid_domain_label",
            )

    tld = parts[-1]

    if not re.fullmatch(r"[a-z]{2,63}", tld):
        return DomainValidationResult(
            domain=domain,
            domain_type=DomainType.INVALID,
            valid=False,
            reason="invalid_tld",
        )

    return DomainValidationResult(
        domain=domain,
        domain_type=DomainType.PUBLIC,
        valid=True,
        reason="syntactically_valid_public_domain",
    )