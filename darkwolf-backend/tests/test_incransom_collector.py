from app.sites.inc_ransom.collector import (
    IncRansomCollector,
)


collector = IncRansomCollector()

announcements = collector.collect_page(
    page=1,
    per_page=3,
)

print(
    f"\nCollected: {len(announcements)}"
)

for announcement in announcements:

    print("\n" + "=" * 60)

    print(
        "ID:",
        announcement.id,
    )

    print(
        "Company:",
        announcement.company.name,
    )

    print(
        "Company ID:",
        announcement.company.id,
    )

    print(
        "Country:",
        announcement.company.country,
    )

    print(
        "Revenue:",
        announcement.company.revenue,
    )

    print(
        "Categories:",
        announcement.categories,
    )

    print(
        "Proof IDs:",
        announcement.proof_ids,
    )

    print(
        "Visits:",
        announcement.visits,
    )

    print(
        "Leak At:",
        announcement.leak_at,
    )

    print(
        "Created:",
        announcement.created_at,
    )

    print(
        "Updated:",
        announcement.updated_at,
    )

    print(
        "Description:",
        announcement.descriptions,
    )