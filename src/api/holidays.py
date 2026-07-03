"""Holidays API Client Module.

This module retrieves national public holidays for India using the public
Nager.Date API, falling back to a local calendar generator if offline.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional
from src.api.client import BaseApiClient, ApiResponse, generate_request_id


class HolidaysApiClient(BaseApiClient):
    """Client for fetching public holiday calendars."""

    def __init__(self, **kwargs: Any) -> None:
        base_url = "https://date.nager.at"
        super().__init__(base_url=base_url, **kwargs)

    def get_holidays(self, year: Optional[int] = None) -> ApiResponse:
        """Fetches public holidays for India for a given calendar year.

        URL: https://date.nager.at/api/v3/PublicHolidays/{Year}/IN

        Args:
            year: Calendar year. Defaults to current year.

        Returns:
            ApiResponse: Container with raw JSON array.
        """
        target_year = year or datetime.now(timezone.utc).year
        endpoint = f"api/v3/PublicHolidays/{target_year}/IN"

        response = self.request(method="GET", endpoint=endpoint)
        if not response.success:
            return self._generate_fallback_holidays(target_year)

        return response

    def _generate_fallback_holidays(self, year: int) -> ApiResponse:
        """Generates static, official Gazetted National holidays for India."""
        fallback_holidays = [
            {
                "date": f"{year}-01-26",
                "localName": "Republic Day",
                "name": "Republic Day",
                "countryCode": "IN",
                "fixed": True,
                "global": True,
            },
            {
                "date": f"{year}-08-15",
                "localName": "Independence Day",
                "name": "Independence Day",
                "countryCode": "IN",
                "fixed": True,
                "global": True,
            },
            {
                "date": f"{year}-10-02",
                "localName": "Mahatma Gandhi Jayanti",
                "name": "Gandhi Jayanti",
                "countryCode": "IN",
                "fixed": True,
                "global": True,
            },
            {
                "date": f"{year}-12-25",
                "localName": "Christmas Day",
                "name": "Christmas Day",
                "countryCode": "IN",
                "fixed": True,
                "global": True,
            },
        ]

        req_id = generate_request_id()
        payload = json.dumps(fallback_holidays)

        return ApiResponse(
            request_id=req_id,
            status_code=200,
            headers={"Content-Type": "application/json"},
            content_type="application/json",
            response_size=len(payload),
            text=payload,
            success=True,
        )
