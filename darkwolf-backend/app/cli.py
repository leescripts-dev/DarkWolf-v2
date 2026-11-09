import argparse
import json


def main():
    parser = argparse.ArgumentParser(
        description="DarkWolf command-line interface"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    collect_parser = subparsers.add_parser(
        "collect",
        help="Run threat intelligence collection",
    )

    collect_parser.add_argument(
        "source",
        choices=["inc-ransom", "ransomware-sites", "api-leak-sites", "javascript-leak-sites"],
        help="Collection source",
    )

    subparsers.add_parser(
        "backfill-html-discoveries",
        help="Create first-observed events for the initial HTML leak-site snapshot",
    )

    subparsers.add_parser(
        "backfill-observation-events",
        help="Reconstruct missing discovery and change events from all saved observations",
    )

    collect_parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="Page number to collect",
    )

    collect_parser.add_argument(
        "--mode",
        choices=["live", "baseline"],
        default="live",
        help="Baseline saves observations without events; live generates change events",
    )

    collect_parser.add_argument(
        "--per-page",
        type=int,
        default=15,
        help="Number of announcements per page",
    )

    args = parser.parse_args()

    if args.command == "collect":
        if args.source == "inc-ransom":
            from app.collection.service import IncRansomCollectionService

            service = IncRansomCollectionService()

            result = service.collect_page(
                page=args.page,
                per_page=args.per_page,
            )

            print(result)

        elif args.source == "ransomware-sites":
            from app.collection.ransomware_sites import RansomwareSitesCollectionService

            result = RansomwareSitesCollectionService().collect(
                baseline=args.mode == "baseline",
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.source == "api-leak-sites":
            from app.collection.ransomware_sites import RansomwareSitesCollectionService
            from app.sites.api_leak_sites.collector import collect_api_site_pages
            from app.sites.api_leak_sites.registry import API_LEAK_SITES

            result = RansomwareSitesCollectionService(
                sites=API_LEAK_SITES,
                collector=collect_api_site_pages,
                collection_source="api_leak_sites",
            ).collect(baseline=args.mode == "baseline")
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.source == "javascript-leak-sites":
            from app.collection.ransomware_sites import RansomwareSitesCollectionService
            from app.sites.javascript_leak_sites.collector import collect_javascript_site_pages
            from app.sites.javascript_leak_sites.registry import JAVASCRIPT_LEAK_SITES

            result = RansomwareSitesCollectionService(
                sites=JAVASCRIPT_LEAK_SITES,
                collector=collect_javascript_site_pages,
                collection_source="javascript_leak_sites",
            ).collect(baseline=args.mode == "baseline")
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    elif args.command == "backfill-html-discoveries":
        from app.collection.baseline_discoveries import backfill_initial_listing_discoveries

        print(json.dumps(backfill_initial_listing_discoveries(), indent=2))

    elif args.command == "backfill-observation-events":
        from app.collection.backfill_observation_events import backfill_observation_events

        print(json.dumps(backfill_observation_events(), indent=2))


if __name__ == "__main__":
    main()
