"""National Power Portal (NPP) API Client Module.

This module fetches plant-level electricity generation outputs (Solar, Wind, Coal, etc.)
from NPP resources on the OGD platform.
"""

from typing import Any, Dict, Optional
from src.api.data_gov import DataGovClient
from src.api.client import ApiResponse
from src.utils.logging_util import logger


class NppApiClient:
    """Client for extracting National Power Portal datasets."""

    # Default resource IDs representing NPP plant-level daily reports on data.gov.in
    DEFAULT_PLANT_GENERATION_RESOURCE = "ed765355-be35-4818-9ae4-8fae10e1c9f8"
    DEFAULT_RENEWABLE_METRICS_RESOURCE = "94f0a6e5-4c74-4b0f-99c6-3e5d5e7e0a3b"

    def __init__(self, data_gov_client: Optional[DataGovClient] = None) -> None:
        """Initializes the NPP API client.

        Args:
            data_gov_client: Optional DataGovClient instance for API queries.
        """
        self.client = data_gov_client or DataGovClient()
        logger.info("NPP API Client initialized")

    def get_daily_generation_by_plant(
        self,
        resource_id: Optional[str] = None,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> ApiResponse:
        """Extracts plant-wise daily electricity generation outputs.

        Args:
            resource_id: Custom resource ID.
            limit: Record limits.
            filters: Filter keys (e.g. filtering by fuel type like Coal, Hydro).

        Returns:
            ApiResponse: Container with raw response.
        """
        res_id = resource_id or self.DEFAULT_PLANT_GENERATION_RESOURCE
        logger.info(f"Fetching NPP daily plant generation (limit={limit})")
        return self.client.fetch_resource(
            resource_id=res_id, limit=limit, extra_params=filters
        )

    def get_renewable_generation_summary(
        self,
        resource_id: Optional[str] = None,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> ApiResponse:
        """Extracts summary profiles for renewable energy generation (Solar & Wind).

        Args:
            resource_id: Custom resource ID.
            limit: Record limits.
            filters: Filter keys (e.g. state-level filters).

        Returns:
            ApiResponse: Container with raw response.
        """
        res_id = resource_id or self.DEFAULT_RENEWABLE_METRICS_RESOURCE
        logger.info(f"Fetching NPP renewable generation summary (limit={limit})")
        return self.client.fetch_resource(
            resource_id=res_id, limit=limit, extra_params=filters
        )
