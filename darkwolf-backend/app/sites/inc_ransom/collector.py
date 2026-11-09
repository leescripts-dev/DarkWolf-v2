from app.collectors.tor import TorClient
from app.core.config import settings
from app.sites.inc_ransom.models import IncRansomAnnouncement
from app.sites.inc_ransom.parser import parse_announcement


class IncRansomCollector:
    def __init__(self, client: TorClient | None = None):
        self.client = client or TorClient()
        self.api_base_url = settings.inc_ransom_api_base_url

    def get_announcements_page(
        self,
        page: int = 1,
        per_page: int = 15,
    ):
        url = f"{self.api_base_url}/announcements"

        response = self.client.get(
            f"{url}?page={page}&perPage={per_page}"
        )

        return response

    def get_announcement(
        self,
        announcement_id: str,
    ):
        url = (
            f"{self.api_base_url}"
            f"/announcement/{announcement_id}"
        )

        response = self.client.get(url)

        return response

    def get_disclosures(
        self,
        announcement_id: str,
    ):
        url = (
            f"{self.api_base_url}"
            f"/disclosures/{announcement_id}"
        )

        response = self.client.get(url)

        return response

    def collect_page(
        self,
        page: int = 1,
        per_page: int = 15,
    ) -> list[IncRansomAnnouncement]:

        listing_response = self.get_announcements_page(
            page=page,
            per_page=per_page,
        )

        listing_data = listing_response.json()

        announcements = (
            listing_data
            .get("payload", {})
            .get("announcements", [])
        )

        results = []

        for listing_item in announcements:
            announcement_id = listing_item.get("_id")

            if not announcement_id:
                continue

            detail_response = self.get_announcement(
                announcement_id
            )

            detail_data = detail_response.json()

            detail = detail_data.get("payload")

            if not detail:
                continue

            country = (
                listing_item
                .get("company", {})
                .get("country")
            )

            announcement = parse_announcement(
                detail,
                existing_country=country,
            )

            results.append(announcement)

        return results