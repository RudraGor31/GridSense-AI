"""Central Constants Module for GridSense AI.

This module defines all global constants used across the ingestion pipeline,
including API endpoints, timeout thresholds, data format standards, and
execution thresholds.
"""

from typing import Dict, List

# ============================================================================
# REQUEST ID AND TRACING CONSTANTS
# ============================================================================

REQUEST_ID_PREFIX = "GS"
REQUEST_ID_DATE_FORMAT = "%Y%m%d"
REQUEST_ID_SEQUENCE_WIDTH = 6

# ============================================================================
# HTTP CLIENT CONSTANTS
# ============================================================================

DEFAULT_USER_AGENT = "GridSenseAI-Ingestion/2.1.0 (Contact: local-developer)"
DEFAULT_ACCEPT_HEADERS = "application/json, text/csv, application/xml"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF_FACTOR = 2.0

# HTTP status codes
HTTP_SUCCESS_START = 200
HTTP_SUCCESS_END = 299
HTTP_REDIRECT_START = 300
HTTP_REDIRECT_END = 399
HTTP_CLIENT_ERROR_START = 400
HTTP_CLIENT_ERROR_END = 499
HTTP_SERVER_ERROR_START = 500
HTTP_SERVER_ERROR_END = 599

# Retryable status codes
RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]

# ============================================================================
# STORAGE AND FILE CONSTANTS
# ============================================================================

RAW_DATA_PARTITION_FORMAT = "source/YYYY/MM/DD"
FILE_NAMING_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
METADATA_LOG_FILENAME = "extraction_metadata.jsonl"
PIPELINE_SUMMARY_FILENAME = "pipeline_summaries.jsonl"

# Supported file formats for raw data storage
SUPPORTED_FILE_FORMATS = ["json", "csv", "xml", "txt"]

# ============================================================================
# LOGGING CONSTANTS
# ============================================================================

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FILE = "gridsense.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(module)s.%(funcName)s | %(message)s"
LOG_TIMEZONE = "UTC"

# Rotating file handler settings
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 5

# ============================================================================
# DATA SOURCE CONFIGURATIONS
# ============================================================================

# Available API sources in the ingestion pipeline
DATA_SOURCES = {
    "cea": {
        "name": "Central Electricity Authority",
        "base_url": "https://cea.nic.in",
        "timeout": 15,
        "max_retries": 5,
        "description": "Indian power generation and demand statistics",
    },
    "npp": {
        "name": "National Power Portal",
        "base_url": "https://www.npp.gov.in",
        "timeout": 15,
        "max_retries": 5,
        "description": "Real-time power system operations",
    },
    "open_meteo": {
        "name": "Open-Meteo Weather API",
        "base_url": "https://api.open-meteo.com/v1",
        "timeout": 15,
        "max_retries": 5,
        "description": "Weather and meteorological data",
    },
    "waqi": {
        "name": "World Air Quality Index",
        "base_url": "https://api.waqi.info",
        "timeout": 15,
        "max_retries": 5,
        "description": "Air quality measurements",
    },
    "world_bank": {
        "name": "World Bank Open Data",
        "base_url": "https://api.worldbank.org",
        "timeout": 20,
        "max_retries": 5,
        "description": "Economic and development indicators",
    },
    "data_gov": {
        "name": "Data.gov.in API",
        "base_url": "https://api.data.gov.in",
        "timeout": 15,
        "max_retries": 5,
        "description": "Indian government datasets",
    },
    "census": {
        "name": "Census of India Data",
        "base_url": "https://censusindia.gov.in",
        "timeout": 20,
        "max_retries": 5,
        "description": "Population and demographic data",
    },
    "holidays": {
        "name": "Nager.Date Holidays API",
        "base_url": "https://date.nager.at",
        "timeout": 10,
        "max_retries": 3,
        "description": "Indian public holidays",
    },
    "vahan": {
        "name": "VAHAN EV Registry",
        "base_url": "https://vahan.parivahan.gov.in",
        "timeout": 20,
        "max_retries": 5,
        "description": "Electric vehicle registration statistics",
    },
}

# ============================================================================
# GEOGRAPHIC AND DEMOGRAPHIC CONSTANTS
# ============================================================================

# Indian states for geographic partitioning and reference
INDIAN_STATES = [
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
]

# Union Territories
UNION_TERRITORIES = [
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Lakshadweep",
    "Delhi",
    "Puducherry",
    "Ladakh",
    "Jammu and Kashmir",
]

# State capital coordinates for geographic data extraction
STATE_CAPITALS: Dict[str, Dict[str, float]] = {
    "Andhra Pradesh": {"latitude": 13.1939, "longitude": 79.7751},
    "Arunachal Pradesh": {"latitude": 28.2180, "longitude": 92.9383},
    "Assam": {"latitude": 26.1445, "longitude": 91.7362},
    "Bihar": {"latitude": 25.5941, "longitude": 85.1376},
    "Chhattisgarh": {"latitude": 21.2514, "longitude": 81.6296},
    "Goa": {"latitude": 15.3009, "longitude": 73.8315},
    "Gujarat": {"latitude": 23.1815, "longitude": 72.6369},
    "Haryana": {"latitude": 29.0588, "longitude": 77.0745},
    "Himachal Pradesh": {"latitude": 31.7846, "longitude": 76.2294},
    "Jharkhand": {"latitude": 23.3441, "longitude": 85.3096},
    "Karnataka": {"latitude": 12.9716, "longitude": 77.5946},
    "Kerala": {"latitude": 8.5241, "longitude": 76.9366},
    "Madhya Pradesh": {"latitude": 23.1815, "longitude": 79.9864},
    "Maharashtra": {"latitude": 18.9690, "longitude": 72.8210},
    "Manipur": {"latitude": 24.6637, "longitude": 93.9063},
    "Meghalaya": {"latitude": 25.5788, "longitude": 91.8933},
    "Mizoram": {"latitude": 23.8103, "longitude": 93.0107},
    "Nagaland": {"latitude": 25.6687, "longitude": 93.9063},
    "Odisha": {"latitude": 20.2961, "longitude": 85.8245},
    "Punjab": {"latitude": 31.5497, "longitude": 74.3436},
    "Rajasthan": {"latitude": 26.9124, "longitude": 75.7873},
    "Sikkim": {"latitude": 27.5330, "longitude": 88.6139},
    "Tamil Nadu": {"latitude": 13.0827, "longitude": 80.2707},
    "Telangana": {"latitude": 17.3850, "longitude": 78.4867},
    "Tripura": {"latitude": 23.8137, "longitude": 91.2868},
    "Uttar Pradesh": {"latitude": 26.8467, "longitude": 80.9462},
    "Uttarakhand": {"latitude": 30.1266, "longitude": 79.6293},
    "West Bengal": {"latitude": 22.5726, "longitude": 88.3639},
    "Delhi": {"latitude": 28.7041, "longitude": 77.1025},
}

# ============================================================================
# EXECUTION THRESHOLDS AND TIMEOUTS
# ============================================================================

# Pipeline execution constraints
PIPELINE_MAX_CONCURRENT_REQUESTS = 5
PIPELINE_TIMEOUT_SECONDS = 3600  # 1 hour
PIPELINE_BATCH_SIZE = 10

# Data validation thresholds
MIN_RESPONSE_SIZE_BYTES = 10  # Minimum acceptable response size
MAX_RESPONSE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB

# ============================================================================
# METADATA AND AUDIT CONSTANTS
# ============================================================================

# Metadata fields tracked for each request
METADATA_FIELDS: List[str] = [
    "timestamp",
    "source_name",
    "endpoint",
    "request_id",
    "status_code",
    "success",
    "execution_time_ms",
    "response_size_bytes",
    "file_path",
    "sha256_checksum",
    "row_count",
    "error_message",
    "content_type",
]

# Pipeline summary statistics
PIPELINE_SUMMARY_FIELDS: List[str] = [
    "execution_start",
    "execution_end",
    "runtime_seconds",
    "apis_attempted",
    "successful_extractions",
    "failed_extractions",
    "total_rows_downloaded",
    "files_created",
    "warnings_count",
    "errors_count",
]

# ============================================================================
# ERROR CODES AND MESSAGES
# ============================================================================

ERROR_MESSAGES: Dict[str, str] = {
    "TIMEOUT": "Request exceeded timeout threshold",
    "CONNECTION_ERROR": "Failed to establish connection to API endpoint",
    "INVALID_RESPONSE": "Response format does not match expected schema",
    "AUTH_FAILURE": "Authentication failed - invalid or expired credentials",
    "RATE_LIMITED": "API rate limit exceeded",
    "SERVER_ERROR": "API server returned 5xx error",
    "PARTIAL_DATA": "Incomplete data received from API",
    "PARSE_ERROR": "Failed to parse API response",
}

# ============================================================================
# CACHE AND OPTIMIZATION CONSTANTS
# ============================================================================

# Cache TTL (Time-To-Live) for different data types
CACHE_TTL_SECONDS: Dict[str, int] = {
    "static_data": 86400,  # 24 hours
    "dynamic_data": 3600,  # 1 hour
    "real_time_data": 300,  # 5 minutes
}

# ============================================================================
# FEATURE FLAGS AND EXPERIMENTAL SETTINGS
# ============================================================================

# Feature flags for experimental or optional features
FEATURE_FLAGS: Dict[str, bool] = {
    "ENABLE_COMPRESSION": True,
    "ENABLE_CACHING": False,
    "ENABLE_BATCH_PROCESSING": True,
    "ENABLE_METADATA_LINEAGE": True,
}
