from app.sites.inc_ransom.collector import (
    IncRansomCollector,
)
from app.snapshots.manager import (
    build_observation,
)


collector = IncRansomCollector()

announcements = collector.collect_page(
    page=1,
    per_page=3,
)

for announcement in announcements:

    observation = build_observation(
        announcement
    )

    print("\n" + "=" * 60)

    print(
        "Source:",
        observation.source,
    )

    print(
        "Source ID:",
        observation.source_id,
    )

    print(
        "Company:",
        observation.company_name,
    )

    print(
        "Visits:",
        observation.visits,
    )

    print(
        "Content Hash:",
        observation.content_hash,
    )