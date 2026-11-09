from uuid import uuid4

from app.collectors.tor import TorClient

from app.collection.result import (
    CollectionResult,
    HistoricalCollectionResult,
)

from app.db.disclosure_observations import (
    get_latest_disclosure_observation,
    save_disclosure_observation,
)
from app.db.events import save_event
from app.db.observations import (
    get_latest_observation,
    save_observation,
)
from app.db.raw_evidence import save_raw_evidence

from app.events.detector import detect_events
from app.events.disclosure_detector import (
    detect_disclosure_events,
)

from app.models.event import ThreatEvent

from app.snapshots.differ import compare_observations
from app.snapshots.disclosure_differ import (
    compare_disclosures,
)
from app.snapshots.disclosure_manager import (
    build_disclosure_observation,
)
from app.snapshots.evidence import build_raw_evidence
from app.snapshots.manager import build_observation

from app.sites.inc_ransom.collector import (
    IncRansomCollector,
)
from app.sites.inc_ransom.disclosure_parser import (
    parse_disclosure,
)
from app.sites.inc_ransom.parser import (
    parse_announcement,
)


class IncRansomCollectionService:
    def __init__(
        self,
        collector: IncRansomCollector | None = None,
    ):
        self.collector = (
            collector
            or IncRansomCollector(
                client=TorClient()
            )
        )

    # =========================================================
    # LIVE PAGINATED COLLECTION
    # =========================================================

    def collect_page(
        self,
        page: int = 1,
        per_page: int = 15,
    ) -> CollectionResult:
        collection_run_id = str(uuid4())

        result = CollectionResult(
            collection_run_id=collection_run_id,
            source="inc_ransom",
            page=page,
        )

        listing_response = (
            self.collector.get_announcements_page(
                page=page,
                per_page=per_page,
            )
        )

        listing_evidence = build_raw_evidence(
            source="inc_ransom",
            source_id=None,
            collection_run_id=collection_run_id,
            endpoint=str(listing_response.url),
            response=listing_response,
            metadata={
                "type": "announcement_listing",
                "page": page,
                "per_page": per_page,
            },
        )

        save_raw_evidence(listing_evidence)

        listing_data = listing_response.json()

        announcements = (
            listing_data
            .get("payload", {})
            .get("announcements", [])
        )

        result.announcements_found = len(
            announcements
        )

        for listing_item in announcements:
            announcement_id = listing_item.get("_id")

            if not announcement_id:
                continue

            try:
                self._process_announcement(
                    listing_item=listing_item,
                    announcement_id=announcement_id,
                    collection_run_id=collection_run_id,
                    result=result,
                )

            except Exception as exc:
                result.errors.append({
                    "source_id": announcement_id,
                    "error": str(exc),
                })

        return result

    # =========================================================
    # HISTORICAL BASELINE COLLECTION
    # =========================================================

    def collect_all_historical(
        self,
        per_page: int = 15,
    ) -> HistoricalCollectionResult:
        """
        Build the initial historical baseline from all
        currently available Inc Ransom announcements.

        Historical ingestion:
        - Preserves raw listing/detail evidence.
        - Creates observations.
        - Performs change comparison.
        - Does NOT generate semantic events.
        - Does NOT collect disclosures.

        This establishes the historical observation baseline
        without generating artificial VICTIM_DISCOVERED events.
        """

        collection_run_id = str(uuid4())

        result = HistoricalCollectionResult(
            collection_run_id=collection_run_id,
            source="inc_ransom",
        )

        # -----------------------------------------------------
        # Fetch first page.
        # -----------------------------------------------------

        first_page_response = (
            self.collector.get_announcements_page(
                page=1,
                per_page=per_page,
            )
        )

        first_page_evidence = build_raw_evidence(
            source="inc_ransom",
            source_id=None,
            collection_run_id=collection_run_id,
            endpoint=str(first_page_response.url),
            response=first_page_response,
            metadata={
                "type": "announcement_listing",
                "mode": "historical",
                "page": 1,
                "per_page": per_page,
            },
        )

        save_raw_evidence(first_page_evidence)

        first_page_data = first_page_response.json()

        payload = first_page_data.get(
            "payload",
            {},
        )

        total_announcements = payload.get(
            "length",
            0,
        )

        if not isinstance(total_announcements, int):
            raise ValueError(
                "Invalid announcement count returned by Inc Ransom"
            )

        result.announcements_expected = (
            total_announcements
        )

        if total_announcements == 0:
            return result

        # -----------------------------------------------------
        # Calculate expected pages.
        # -----------------------------------------------------

        expected_pages = (
            (total_announcements + per_page - 1)
            // per_page
        )

        result.expected_pages = expected_pages

        # -----------------------------------------------------
        # Process page 1.
        # -----------------------------------------------------

        self._process_historical_page(
            page=1,
            page_data=first_page_data,
            collection_run_id=collection_run_id,
            result=result,
        )

        # -----------------------------------------------------
        # Process remaining pages.
        # -----------------------------------------------------

        for page in range(
            2,
            expected_pages + 1,
        ):
            try:
                response = (
                    self.collector.get_announcements_page(
                        page=page,
                        per_page=per_page,
                    )
                )

                evidence = build_raw_evidence(
                    source="inc_ransom",
                    source_id=None,
                    collection_run_id=collection_run_id,
                    endpoint=str(response.url),
                    response=response,
                    metadata={
                        "type": "announcement_listing",
                        "mode": "historical",
                        "page": page,
                        "per_page": per_page,
                    },
                )

                save_raw_evidence(evidence)

                page_data = response.json()

                self._process_historical_page(
                    page=page,
                    page_data=page_data,
                    collection_run_id=collection_run_id,
                    result=result,
                )

            except Exception as exc:
                result.errors.append({
                    "page": page,
                    "error": str(exc),
                })

        return result

    def _process_historical_page(
        self,
        page: int,
        page_data: dict,
        collection_run_id: str,
        result: HistoricalCollectionResult,
    ):
        """
        Process one historical announcement listing page.

        No semantic events are generated.
        """

        announcements = (
            page_data
            .get("payload", {})
            .get("announcements", [])
        )

        result.pages_processed += 1

        result.announcements_found += len(
            announcements
        )

        for listing_item in announcements:
            announcement_id = listing_item.get(
                "_id"
            )

            if not announcement_id:
                result.errors.append({
                    "page": page,
                    "error": (
                        "Announcement missing _id"
                    ),
                })
                continue

            try:
                self._process_historical_announcement(
                    listing_item=listing_item,
                    announcement_id=announcement_id,
                    collection_run_id=collection_run_id,
                    result=result,
                )

            except Exception as exc:
                result.errors.append({
                    "page": page,
                    "source_id": announcement_id,
                    "error": str(exc),
                })

    def _process_historical_announcement(
        self,
        listing_item: dict,
        announcement_id: str,
        collection_run_id: str,
        result: HistoricalCollectionResult,
    ):
        """
        Fetch and persist one historical announcement.

        Historical mode intentionally:
        - saves raw evidence
        - saves an observation
        - compares against previous observations
        - does NOT generate semantic events
        - does NOT collect disclosures
        """

        # -----------------------------------------------------
        # Fetch announcement detail.
        # -----------------------------------------------------

        detail_response = (
            self.collector.get_announcement(
                announcement_id
            )
        )

        # -----------------------------------------------------
        # Preserve raw detail evidence.
        # -----------------------------------------------------

        detail_evidence = build_raw_evidence(
            source="inc_ransom",
            source_id=announcement_id,
            collection_run_id=collection_run_id,
            endpoint=str(detail_response.url),
            response=detail_response,
            metadata={
                "type": "announcement_detail",
                "mode": "historical",
            },
        )

        raw_evidence_id = save_raw_evidence(
            detail_evidence
        )

        # -----------------------------------------------------
        # Parse API response.
        # -----------------------------------------------------

        detail_data = detail_response.json()

        detail = detail_data.get(
            "payload"
        )

        if not detail:
            raise ValueError(
                "Announcement detail payload missing"
            )

        country = (
            listing_item
            .get("company", {})
            .get("country")
        )

        announcement = parse_announcement(
            detail,
            existing_country=country,
        )

        # -----------------------------------------------------
        # Build observation.
        # -----------------------------------------------------

        observation = build_observation(
            announcement=announcement,
            collection_run_id=collection_run_id,
            raw_evidence_id=raw_evidence_id,
        )

        # -----------------------------------------------------
        # Compare against latest existing observation.
        # -----------------------------------------------------

        previous = get_latest_observation(
            source="inc_ransom",
            source_id=announcement.id,
        )

        comparison = compare_observations(
            previous=previous,
            current=observation.model_dump(),
        )

        # -----------------------------------------------------
        # Persist observation.
        # -----------------------------------------------------

        save_observation(
            observation
        )

        result.observations_saved += 1

        # -----------------------------------------------------
        # Update historical counters.
        # -----------------------------------------------------

        change_type = comparison.get(
            "change_type"
        )

        if change_type == "FIRST_OBSERVATION":
            result.first_observations += 1

        elif change_type == "CONTENT_CHANGED":
            result.content_changed += 1

        elif comparison.get("changed") is False:
            result.unchanged += 1

        # -----------------------------------------------------
        # IMPORTANT:
        #
        # No detect_events() here.
        # No disclosure collection here.
        # -----------------------------------------------------

    # =========================================================
    # HISTORICAL SINGLE-ANNOUNCEMENT RETRY
    # =========================================================

    def collect_historical_announcement(
        self,
        announcement_id: str,
    ) -> dict:
        """
        Retry ingestion of one historical announcement.

        Used for historical records that failed during the
        full baseline ingestion.

        This method:
        - fetches the announcement
        - preserves raw evidence
        - parses the announcement
        - builds an observation
        - compares against the latest observation
        - saves the observation

        It intentionally does NOT:
        - generate semantic events
        - collect disclosures
        """

        collection_run_id = str(uuid4())

        # -----------------------------------------------------
        # Fetch announcement detail.
        # -----------------------------------------------------

        detail_response = (
            self.collector.get_announcement(
                announcement_id
            )
        )

        # -----------------------------------------------------
        # Preserve raw evidence.
        # -----------------------------------------------------

        detail_evidence = build_raw_evidence(
            source="inc_ransom",
            source_id=announcement_id,
            collection_run_id=collection_run_id,
            endpoint=str(detail_response.url),
            response=detail_response,
            metadata={
                "type": "announcement_detail",
                "mode": "historical_retry",
            },
        )

        raw_evidence_id = save_raw_evidence(
            detail_evidence
        )

        # -----------------------------------------------------
        # Parse response.
        # -----------------------------------------------------

        detail_data = detail_response.json()

        detail = detail_data.get(
            "payload"
        )

        if not detail:
            raise ValueError(
                "Announcement detail payload missing"
            )

        announcement = parse_announcement(
            detail
        )

        # -----------------------------------------------------
        # Build observation.
        # -----------------------------------------------------

        observation = build_observation(
            announcement=announcement,
            collection_run_id=collection_run_id,
            raw_evidence_id=raw_evidence_id,
        )

        # -----------------------------------------------------
        # Compare against existing observation.
        # -----------------------------------------------------

        previous = get_latest_observation(
            source="inc_ransom",
            source_id=announcement.id,
        )

        comparison = compare_observations(
            previous=previous,
            current=observation.model_dump(),
        )

        # -----------------------------------------------------
        # Persist observation.
        # -----------------------------------------------------

        observation_id = save_observation(
            observation
        )

        return {
            "collection_run_id": collection_run_id,
            "announcement_id": announcement.id,
            "observation_id": observation_id,
            "change_type": comparison.get(
                "change_type"
            ),
            "changed": comparison.get(
                "changed"
            ),
            "changed_fields": comparison.get(
                "changed_fields",
                [],
            ),
        }

    # =========================================================
    # TARGETED ANNOUNCEMENT COLLECTION
    # =========================================================

    def collect_announcement(
        self,
        announcement_id: str,
    ) -> CollectionResult:
        """
        Collect one announcement as a live targeted
        collection.

        Unlike historical ingestion, this method generates
        semantic events and processes disclosures.
        """

        collection_run_id = str(uuid4())

        result = CollectionResult(
            collection_run_id=collection_run_id,
            source="inc_ransom",
            page=0,
        )

        try:
            detail_response = (
                self.collector.get_announcement(
                    announcement_id
                )
            )

            detail_evidence = build_raw_evidence(
                source="inc_ransom",
                source_id=announcement_id,
                collection_run_id=collection_run_id,
                endpoint=str(detail_response.url),
                response=detail_response,
                metadata={
                    "type": "announcement_detail",
                    "targeted": True,
                },
            )

            raw_evidence_id = save_raw_evidence(
                detail_evidence
            )

            detail_data = detail_response.json()

            detail = detail_data.get(
                "payload"
            )

            if not detail:
                raise ValueError(
                    "Announcement detail payload missing"
                )

            announcement = parse_announcement(
                detail
            )

            observation = build_observation(
                announcement=announcement,
                collection_run_id=collection_run_id,
                raw_evidence_id=raw_evidence_id,
            )

            previous = get_latest_observation(
                source="inc_ransom",
                source_id=announcement.id,
            )

            comparison = compare_observations(
                previous=previous,
                current=observation.model_dump(),
            )

            observation_id = save_observation(
                observation
            )

            result.announcements_found = 1
            result.observations_saved += 1

            self._update_announcement_counters(
                comparison=comparison,
                result=result,
            )

            events = detect_events(
                comparison
            )

            for event_data in events:
                event = ThreatEvent(
                    source="inc_ransom",
                    source_id=announcement.id,
                    collection_run_id=collection_run_id,
                    event_type=event_data[
                        "event_type"
                    ],
                    detected_at=(
                        observation.observed_at
                    ),
                    observation_id=observation_id,
                    previous_observation_id=(
                        str(previous["_id"])
                        if previous
                        else None
                    ),
                    changed_fields=event_data[
                        "changed_fields"
                    ],
                    changes=event_data[
                        "changes"
                    ],
                    details=event_data[
                        "details"
                    ],
                )

                save_event(event)

                result.events_generated += 1

            self._process_disclosures(
                announcement_id=announcement.id,
                collection_run_id=collection_run_id,
                result=result,
            )

        except Exception as exc:
            result.errors.append({
                "source_id": announcement_id,
                "error": str(exc),
            })

        return result

    # =========================================================
    # LIVE ANNOUNCEMENT PROCESSING
    # =========================================================

    def _process_announcement(
        self,
        listing_item: dict,
        announcement_id: str,
        collection_run_id: str,
        result: CollectionResult,
    ):
        detail_response = (
            self.collector.get_announcement(
                announcement_id
            )
        )

        detail_evidence = build_raw_evidence(
            source="inc_ransom",
            source_id=announcement_id,
            collection_run_id=collection_run_id,
            endpoint=str(detail_response.url),
            response=detail_response,
            metadata={
                "type": "announcement_detail",
            },
        )

        raw_evidence_id = save_raw_evidence(
            detail_evidence
        )

        detail_data = detail_response.json()

        detail = detail_data.get(
            "payload"
        )

        if not detail:
            raise ValueError(
                "Announcement detail payload missing"
            )

        country = (
            listing_item
            .get("company", {})
            .get("country")
        )

        announcement = parse_announcement(
            detail,
            existing_country=country,
        )

        observation = build_observation(
            announcement=announcement,
            collection_run_id=collection_run_id,
            raw_evidence_id=raw_evidence_id,
        )

        previous = get_latest_observation(
            source="inc_ransom",
            source_id=announcement.id,
        )

        comparison = compare_observations(
            previous=previous,
            current=observation.model_dump(),
        )

        observation_id = save_observation(
            observation
        )

        result.observations_saved += 1

        self._update_announcement_counters(
            comparison=comparison,
            result=result,
        )

        events = detect_events(
            comparison
        )

        for event_data in events:
            event = ThreatEvent(
                source="inc_ransom",
                source_id=announcement.id,
                collection_run_id=collection_run_id,
                event_type=event_data[
                    "event_type"
                ],
                detected_at=(
                    observation.observed_at
                ),
                observation_id=observation_id,
                previous_observation_id=(
                    str(previous["_id"])
                    if previous
                    else None
                ),
                changed_fields=event_data[
                    "changed_fields"
                ],
                changes=event_data[
                    "changes"
                ],
                details=event_data[
                    "details"
                ],
            )

            save_event(event)

            result.events_generated += 1

        self._process_disclosures(
            announcement_id=announcement.id,
            collection_run_id=collection_run_id,
            result=result,
        )

    # =========================================================
    # DISCLOSURE PROCESSING
    # =========================================================

    def _process_disclosures(
        self,
        announcement_id: str,
        collection_run_id: str,
        result: CollectionResult,
    ):
        disclosure_response = (
            self.collector.get_disclosures(
                announcement_id
            )
        )

        disclosure_evidence = build_raw_evidence(
            source="inc_ransom",
            source_id=announcement_id,
            collection_run_id=collection_run_id,
            endpoint=str(disclosure_response.url),
            response=disclosure_response,
            metadata={
                "type": "disclosure",
                "announcement_id": announcement_id,
            },
        )

        disclosure_raw_evidence_id = (
            save_raw_evidence(
                disclosure_evidence
            )
        )

        disclosure_data = (
            disclosure_response.json()
        )

        disclosures = (
            disclosure_data
            .get("payload", [])
        )

        result.disclosures_found += len(
            disclosures
        )

        for disclosure_data_item in disclosures:
            try:
                self._process_disclosure(
                    disclosure_data_item=(
                        disclosure_data_item
                    ),
                    announcement_id=announcement_id,
                    collection_run_id=collection_run_id,
                    raw_evidence_id=(
                        disclosure_raw_evidence_id
                    ),
                    result=result,
                )

            except Exception as exc:
                result.errors.append({
                    "source_id": announcement_id,
                    "disclosure_id": (
                        disclosure_data_item.get(
                            "_id"
                        )
                    ),
                    "error": str(exc),
                })

    def _process_disclosure(
        self,
        disclosure_data_item: dict,
        announcement_id: str,
        collection_run_id: str,
        raw_evidence_id: str,
        result: CollectionResult,
    ):
        disclosure = parse_disclosure(
            disclosure_data_item,
            announcement_id=announcement_id,
        )

        observation = (
            build_disclosure_observation(
                disclosure=disclosure,
                collection_run_id=collection_run_id,
                raw_evidence_id=raw_evidence_id,
            )
        )

        previous = (
            get_latest_disclosure_observation(
                source="inc_ransom",
                disclosure_id=disclosure.id,
            )
        )

        comparison = compare_disclosures(
            previous=previous,
            current=observation.model_dump(),
        )

        observation_id = (
            save_disclosure_observation(
                observation
            )
        )

        result.disclosure_observations_saved += 1

        self._update_disclosure_counters(
            comparison=comparison,
            result=result,
        )

        events = detect_disclosure_events(
            comparison
        )

        for event_data in events:
            event = ThreatEvent(
                source="inc_ransom",
                source_id=announcement_id,
                collection_run_id=collection_run_id,
                event_type=event_data[
                    "event_type"
                ],
                detected_at=(
                    observation.observed_at
                ),
                observation_id=observation_id,
                previous_observation_id=(
                    str(previous["_id"])
                    if previous
                    else None
                ),
                changed_fields=event_data[
                    "changed_fields"
                ],
                changes=event_data[
                    "changes"
                ],
                details={
                    "disclosure_id": disclosure.id,
                    "announcement_id": announcement_id,
                    **event_data["details"],
                },
            )

            save_event(event)

            result.disclosure_events_generated += 1

    # =========================================================
    # COUNTERS
    # =========================================================

    @staticmethod
    def _update_announcement_counters(
        comparison: dict,
        result: CollectionResult,
    ):
        if (
            comparison["change_type"]
            == "FIRST_OBSERVATION"
        ):
            result.first_observations += 1

        elif (
            comparison["change_type"]
            == "CONTENT_CHANGED"
        ):
            result.content_changed += 1

        elif comparison["changed"] is False:
            result.unchanged += 1

    @staticmethod
    def _update_disclosure_counters(
        comparison: dict,
        result: CollectionResult,
    ):
        if (
            comparison["change_type"]
            == "FIRST_OBSERVATION"
        ):
            result.disclosure_first_observations += 1

        elif (
            comparison["change_type"]
            == "CONTENT_CHANGED"
        ):
            result.disclosure_content_changed += 1

        elif comparison["changed"] is False:
            result.disclosure_unchanged += 1