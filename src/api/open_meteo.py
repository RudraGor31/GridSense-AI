"""Open-Meteo Meteorological API Client Module.

This module interfaces with the Open-Meteo Forecast and Historical Archive APIs
to fetch temperature, humidity, rainfall, wind speed, and solar irradiance.
"""

from typing import Any, List, Optional
from src.api.client import BaseApiClient, ApiResponse
from src.utils.logging_util import logger


class OpenMeteoClient(BaseApiClient):
    """Client for querying Open-Meteo weather forecast and archive endpoints."""

    def __init__(self, **kwargs: Any) -> None:
        """Initializes the Open-Meteo API client.

        Args:
            **kwargs: Additional arguments passed to BaseApiClient.
        """
        # We set base URL empty because we target two different subdomains: api. and archive-api.
        super().__init__(base_url="", **kwargs)
        self.default_hourly_variables = [
            "temperature_2m",
            "relative_humidity_2m",
            "rain",
            "direct_normal_irradiance",
            "wind_speed_10m",
        ]
        logger.info("Open-Meteo API Client initialized")

    def get_weather_forecast(
        self,
        latitude: float,
        longitude: float,
        hourly_vars: Optional[List[str]] = None,
        timezone: str = "Asia/Kolkata",
    ) -> ApiResponse:
        """Retrieves a rolling 7-day weather forecast.

        URL: https://api.open-meteo.com/v1/forecast

        Args:
            latitude: Latitude coordinate (WGS84).
            longitude: Longitude coordinate (WGS84).
            hourly_vars: List of hourly weather features to retrieve.
            timezone: Target timezone for timestamps.

        Returns:
            ApiResponse: Container with raw forecast JSON.
        """
        url = "https://api.open-meteo.com/v1/forecast"
        vars_to_fetch = hourly_vars or self.default_hourly_variables

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(vars_to_fetch),
            "timezone": timezone,
        }
        logger.info(f"Fetching weather forecast for ({latitude}, {longitude})")
        return self.request(method="GET", endpoint=url, params=params)

    def get_historical_weather(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        hourly_vars: Optional[List[str]] = None,
        timezone: str = "Asia/Kolkata",
    ) -> ApiResponse:
        """Retrieves historical actual weather measurements for a date range.

        URL: https://archive-api.open-meteo.com/v1/archive

        Args:
            latitude: Latitude coordinate (WGS84).
            longitude: Longitude coordinate (WGS84).
            start_date: Start date string (format YYYY-MM-DD).
            end_date: End date string (format YYYY-MM-DD).
            hourly_vars: List of hourly weather features.
            timezone: Target timezone.

        Returns:
            ApiResponse: Container with raw historical weather JSON.
        """
        url = "https://archive-api.open-meteo.com/v1/archive"
        vars_to_fetch = hourly_vars or self.default_hourly_variables

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(vars_to_fetch),
            "timezone": timezone,
        }
        logger.info(
            f"Fetching historical weather for ({latitude}, {longitude}) from {start_date} to {end_date}"
        )
        return self.request(method="GET", endpoint=url, params=params)
