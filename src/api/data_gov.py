"""Data.gov.in Open Government Data (OGD) Platform Client.

This module provides a client to fetch raw datasets from the official Indian
Open Government Data platform using resource identifiers.
"""

from typing import Any, Dict, Optional
from config.config import config
from src.api.client import BaseApiClient, ApiResponse
from src.utils.logging_util import logger


class DataGovClient(BaseApiClient):
    """Client for interacting with the api.data.gov.in endpoints."""

    def __init__(self, **kwargs: Any) -> None:
        """Initializes the Data.gov.in API client.

        Args:
            **kwargs: Additional arguments passed to BaseApiClient.
        """
        base_url = "https://api.data.gov.in/resource"
        super().__init__(base_url=base_url, **kwargs)
        self.api_key = config.datagov_api_key
        logger.info("Data.gov.in API Client initialized")

    def fetch_resource(
        self,
        resource_id: str,
        limit: int = 100,
        offset: int = 0,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> ApiResponse:
        """Fetches a specific raw dataset resource by its unique identifier.

        URL format: https://api.data.gov.in/resource/{resource_id}

        Args:
            resource_id: Unique hash identifier of the target OGD dataset.
            limit: Maximum records to return.
            offset: Record offset for pagination.
            extra_params: Optional query filter parameters.

        Returns:
            ApiResponse: Container with raw payload and execution metrics.
        """
        params = {
            "api-key": self.api_key,
            "format": "json",
            "limit": limit,
            "offset": offset,
        }
        if extra_params:
            params.update(extra_params)

        logger.info(
            f"Fetching data.gov.in resource {resource_id} (limit={limit}, offset={offset})"
        )
        # The resource path is just the resource ID
        return self.request(method="GET", endpoint=resource_id, params=params)
