from app.entities.domain_service import (
    extract_inc_ransom_domains,
)


def main():
    result = extract_inc_ransom_domains()

    print("\nDOMAIN EXTRACTION")
    print("=" * 50)

    print(
        "Observations processed:",
        result["observations_processed"],
    )

    print(
        "Observations with domains:",
        result["observations_with_domains"],
    )

    print(
        "Unique domains:",
        result["unique_domains"],
    )

    print("\nDOMAINS")

    for domain in result["domains"]:
        print(domain)


if __name__ == "__main__":
    main()