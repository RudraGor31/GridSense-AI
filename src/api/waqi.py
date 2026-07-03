"""World Air Quality Index (WAQI) API Client Module.

This module retrieves real-time and historical Air Quality Index (AQI) data
and chemical pollutant levels (PM2.5, PM10, NO2, SO2, CO, O3) by geographic coordinates.
"""

from typing import Any
from config.config import config
from src.api.client import BaseApiClient, ApiResponse
from src.utils.logging_util import logger


class WaqiApiClient(BaseApiClient):
    """Client for querying the World Air Quality Index (aqicn.org) endpoints."""

    def __init__(self, **kwargs: Any) -> None:
        """Initializes the WAQI API client.

        Args:
            **kwargs: Additional arguments passed to BaseApiClient.
        """
        base_url = "https://api.waqi.info"
        super().__init__(base_url=base_url, **kwargs)
        self.api_token = config.waqi_api_token
        logger.info("WAQI API Client initialized")

    def get_air_quality_by_coordinates(
        self, latitude: float, longitude: float
    ) -> ApiResponse:
        """Retrieves raw AQI and pollutant concentrations for a coordinate.

        URL: https://api.waqi.info/feed/geo:{lat};{lon}/

        Args:
            latitude: Latitude coordinate.
            longitude: Longitude coordinate.

        Returns:
            ApiResponse: Container with raw response JSON.
        """
        # Endpoint path pattern: feed/geo:lat;lon/
        endpoint = f"feed/geo:{latitude};{longitude}/"
        params = {"token": self.api_token}
        logger.info(f"Fetching AQI data for ({latitude}, {longitude})")
        return self.request(method="GET", endpoint=endpoint, params=params)

    def get_air_quality_by_city(self, city_name: str) -> ApiResponse:
        """Retrieves AQI data for a specific city by name.

        URL: https://api.waqi.info/feed/{city}/

        Args:
            city_name: Name of the city (e.g., 'Delhi' or 'Mumbai').

        Returns:
            ApiResponse: Container with raw response JSON.
        """
        endpoint = f"feed/{city_name.lower()}/"
        params = {"token": self.api_token}
        logger.info(f"Fetching AQI data for city: {city_name}")
        return self.request(method="GET", endpoint=endpoint, params=params)
