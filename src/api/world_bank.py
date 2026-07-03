"""World Bank API Client Module.

This module retrieves historical and current macroeconomic indicators (GDP, GDP Growth, etc.)
for India from the World Bank indicators API.
"""

from typing import Any, Dict, Optional
from src.api.client import BaseApiClient, ApiResponse
from src.utils.logging_util import logger


class WorldBankApiClient(BaseApiClient):
    """Client for interacting with the World Bank Open Data API."""

    def __init__(self, **kwargs: Any) -> None:
        """Initializes the World Bank API client.

        Args:
            **kwargs: Additional arguments passed to BaseApiClient.
        """
        base_url = "https://api.worldbank.org/v2"
        super().__init__(base_url=base_url, **kwargs)
        logger.info("World Bank API Client initialized")

    def get_country_indicator(
        self,
        indicator_code: str,
        country_code: str = "IND",
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> ApiResponse:
        """Retrieves an annual economic indicator for a country.

        URL: https://api.worldbank.org/v2/country/{country_code}/indicator/{indicator_code}

        Args:
            indicator_code: The indicator ID (e.g. 'NY.GDP.MKTP.CD' for GDP).
            country_code: Three-letter ISO country code. Defaults to 'IND' (India).
            start_year: Optional starting year filter.
            end_year: Optional ending year filter.

        Returns:
            ApiResponse: Container with raw response JSON.
        """
        endpoint = f"country/{country_code}/indicator/{indicator_code}"
        params: Dict[str, Any] = {"format": "json", "per_page": 1000}

        # Apply year filters
        if start_year and end_year:
            params["date"] = f"{start_year}:{end_year}"
        elif start_year:
            params["date"] = str(start_year)

        logger.info(
            f"Fetching World Bank indicator {indicator_code} for {country_code}"
        )
        return self.request(method="GET", endpoint=endpoint, params=params)

    def get_multiple_indicators(
        self, indicator_codes: list, country_code: str = "IND"
    ) -> Dict[str, ApiResponse]:
        """Fetches multiple indicators for a country.

        Args:
            indicator_codes: List of indicator codes to retrieve.
            country_code: Country code (default 'IND').

        Returns:
            Dictionary mapping indicator codes to ApiResponse objects.
        """
        results = {}
        for code in indicator_codes:
            results[code] = self.get_country_indicator(code, country_code)
        return results
