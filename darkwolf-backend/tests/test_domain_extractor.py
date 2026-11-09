from app.entities.domain_extractor import extract_domains


def main():
    text = """
    Visit https://example.com/company/security
    or www.example.org for more information.

    Another reference is portal.example.com/login.

    We should not duplicate example.com.
    """

    domains = extract_domains(text)

    print("Extracted domains:")
    for domain in domains:
        print(domain)


if __name__ == "__main__":
    main()