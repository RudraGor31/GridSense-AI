"""GridSense AI API Integration Package.

This package exposes the core BaseApiClient and the specific sub-modules for
each government, weather, air quality, demographic, and holiday API.
"""

from src.api.client import BaseApiClient, ApiResponse, generate_request_id
from src.api.data_gov import DataGovClient
from src.api.cea import CeaApiClient
from src.api.npp import NppApiClient
from src.api.open_meteo import OpenMeteoClient
from src.api.waqi import WaqiApiClient
from src.api.world_bank import WorldBankApiClient
from src.api.census import CensusDataExtractor
from src.api.holidays import HolidaysApiClient
from src.api.vahan import VahanEvExtractor

__all__ = [
    "BaseApiClient",
    "ApiResponse",
    "generate_request_id",
    "DataGovClient",
    "CeaApiClient",
    "NppApiClient",
    "OpenMeteoClient",
    "WaqiApiClient",
    "WorldBankApiClient",
    "CensusDataExtractor",
    "HolidaysApiClient",
    "VahanEvExtractor",
]
