"""Central Electricity Authority (CEA) API Client Module.

This module fetches power supply position and conventional generation statistics
from CEA resources on the OGD platform.
"""

from typing import Any, Dict, Optional
from src.api.data_gov import DataGovClient
from src.api.client import ApiResponse
from src.utils.logging_util import logger


class CeaApiClient:
    """Client for extracting Central Electricity Authority datasets."""

    # Default resource IDs from data.gov.in
    # These IDs represent typical CEA Power Supply Position and Installed Capacity datasets
    DEFAULT_DAILY_SUPPLY_RESOURCE = "3aa6a6d9-b1eb-4619-833c-6e0b0e2e4beb"
    DEFAULT_INSTALLED_CAPACITY_RESOURCE = "14d9c1e9-0f29-4f77-ba63-e9a94d15b6c0"

    def __init__(self, data_gov_client: Optional[DataGovClient] = None) -> None:
        """Initializes the CEA API client.

        Args:
            data_gov_client: Optional DataGovClient instance for API queries.
        """
        self.client = data_gov_client or DataGovClient()
        logger.info("CEA API Client initialized")

    def get_daily_power_supply_position(
        self,
        resource_id: Optional[str] = None,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> ApiResponse:
        """Extracts the daily power supply position (energy and peak demand).

        Args:
            resource_id: Custom resource ID. Defaults to standard daily supply ID.
            limit: Record limits.
            filters: Filter keys (e.g., regional query parameters).

        Returns:
            ApiResponse: Container with raw response.
        """
        res_id = resource_id or self.DEFAULT_DAILY_SUPPLY_RESOURCE
        logger.info(f"Fetching CEA daily power supply position (limit={limit})")
        return self.client.fetch_resource(
            resource_id=res_id, limit=limit, extra_params=filters
        )

    def get_installed_capacity(
        self,
        resource_id: Optional[str] = None,
        limit: int = 50,
        filters: Optional[Dict[str, Any]] = None,
    ) -> ApiResponse:
        """Extracts state-wise and region-wise installed generation capacity.

        Args:
            resource_id: Custom resource ID.
            limit: Record limits.
            filters: Filter keys.

        Returns:
            ApiResponse: Container with raw response.
        """
        res_id = resource_id or self.DEFAULT_INSTALLED_CAPACITY_RESOURCE
        logger.info(f"Fetching CEA installed capacity (limit={limit})")
        return self.client.fetch_resource(
            resource_id=res_id, limit=limit, extra_params=filters
        )
