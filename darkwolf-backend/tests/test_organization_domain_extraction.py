from app.entities.organization_domain_service import (
    extract_inc_ransom_organization_domains,
)


def main():
    result = extract_inc_ransom_organization_domains()

    print("\nORGANIZATION + DOMAIN EXTRACTION")
    print("=" * 70)

    print(
        "Observations processed:",
        result["observations_processed"],
    )

    print(
        "Organizations found:",
        result["organizations_found"],
    )

    print(
        "Domains found:",
        result["domains_found"],
    )

    print("\nFINDINGS")
    print("-" * 70)

    for finding in result["findings"]:
        domains = (
            ", ".join(finding.domains)
            if finding.domains
            else "N/A"
        )

        print(
            f"Organization : {finding.organization_name}"
        )
        print(
            f"Domain       : {domains}"
        )
        print(
            f"Source ID    : {finding.source_id}"
        )
        print(
            f"Evidence     : {finding.evidence_type}"
        )
        print(
            f"Observed At  : {finding.observed_at}"
        )
        print("-" * 70)


if __name__ == "__main__":
    main()