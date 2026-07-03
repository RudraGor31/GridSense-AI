# GridSense AI – Smart Energy Intelligence Platform
## Phase 3: Production-Grade API Ingestion Layer

This repository contains the **production-grade data extraction and API integration framework** for **GridSense AI**. The platform is designed to ingest energy, meteorological, environmental, and demographic data across India's regional power grids and store them in an immutable raw storage layer.

**Status:** ✅ Phase 3 IMPLEMENTATION COMPLETE

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Directory Structure](#directory-structure)
3. [Core Components](#core-components)
4. [Installation & Setup](#installation--setup)
5. [Usage Examples](#usage-examples)
6. [Configuration](#configuration)
7. [API Clients](#api-clients)
8. [Data Pipeline](#data-pipeline)
9. [Testing](#testing)
10. [Quality Standards](#quality-standards)
11. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The ingestion architecture is built around the **Single Responsibility Principle (SRP)**, **Immutable Storage**, and **Production-Grade Reliability** to ensure pipeline auditability, resilience, and data integrity.

### Key Pillars

* **API Client Decoupling:** Every data source (CEA, NPP, Open-Meteo, WAQI, World Bank, Census, Nager.Date, VAHAN) is isolated in its own sub-module extending a common `BaseApiClient` class.

* **Request Tracing:** Every HTTP execution is assigned a unique Request ID in format `GS-YYYYMMDD-XXXXXX` (e.g., `GS-20260703-000001`) that is shared across:
  - Console output (via rotating logs)
  - File-based logs (`logs/gridsense.log`)
  - Metadata ledger (`data/raw/extraction_metadata.jsonl`)
  - Pipeline summaries (`data/raw/pipeline_summaries.jsonl`)

* **Immutable File Storage:** Ingested files are stored as read-only historical snapshots with:
  - Hierarchical partitioning: `data/raw/{source_name}/{YYYY}/{MM}/{DD}/`
  - Unique request trace stamps in filenames for auditability
  - SHA-256 checksums calculated instantly upon file write
  - Atomic file writes to prevent partial/corrupted data

* **Resilient Failover:** The client handles:
  - Rate-limiting (HTTP 429)
  - Connection timeouts
  - Server errors (HTTP 500-599)
  - Using custom exponential backoff with randomized jitter
  - Configurable retry policies with fallback to static reference data

---

## Directory Structure

```
GridSense-AI/
├── config/
│   └── config.py                    # Centralized configuration with type hints
│
├── data/
│   ├── raw/                         # Immutable raw API responses
│   │   ├── cea/2026/07/03/          # Source/Date partitioned storage
│   │   ├── weather/2026/07/03/
│   │   ├── extraction_metadata.jsonl # Request-level audit trail
│   │   └── pipeline_summaries.jsonl # Execution statistics
│   ├── processed/                   # Reserved for Phase 4
│   └── parquet/                     # Reserved for Phase 4
│
├── database/
│   ├── sqlite/                      # OLTP metadata databases
│   └── duckdb/                      # OLAP time-series databases
│
├── docs/
│   ├── data_dictionary.md           # Schema specifications
│   └── installation.md              # Deployment guide
│
├── logs/
│   ├── gridsense.log                # Rotating main log file
│   ├── gridsense.log.1              # Backup logs (5 total)
│   └── gridsense.log.2
│
├── reports/                         # Reserved for dashboards
│
├── src/
│   ├── api/
│   │   ├── __init__.py              # Package initialization
│   │   ├── client.py                # BaseApiClient with retries/exponential backoff
│   │   ├── cea.py                   # Central Electricity Authority
│   │   ├── census.py                # Demographic data with fallback
│   │   ├── data_gov.py              # data.gov.in generic resource reader
│   │   ├── holidays.py              # Indian public holidays
│   │   ├── npp.py                   # National Power Portal
│   │   ├── open_meteo.py            # Weather forecasts & historical
│   │   ├── vahan.py                 # EV registration statistics
│   │   ├── waqi.py                  # Air Quality Index
│   │   └── world_bank.py            # Economic indicators
│   │
│   ├── utils/
│   │   ├── helpers.py               # Path handling, checksums, atomic writes
│   │   └── logging_util.py          # Console + rotating file handlers
│   │
│   ├── constants.py                 # Central constants (endpoints, timeouts)
│   └── metadata.py                  # Metadata ledger & pipeline summaries
│
├── tests/
│   ├── __init__.py
│   ├── test_client.py               # BaseApiClient tests
│   └── test_integration.py          # Comprehensive integration tests
│
├── .env.example                     # Configuration template
├── .gitignore
├── README.md                        # This file
├── requirements.txt                 # Python dependencies
└── run_ingest.py                    # Main orchestrator script
```

---

## Core Components

### 1. Configuration Management (`config/config.py`)

Centralized configuration with environment variable parsing and validation:

```python
from config.config import config

# Access configuration
print(config.api_timeout)         # 15.0 seconds
print(config.api_max_retries)     # 5
print(config.raw_data_dir)        # Path to data/raw/
print(config.datagov_api_key)     # From .env or env variable
```

**Validates:**
- Writable directories
- API key presence (non-fatal warnings)
- File format settings
- Timeout and retry thresholds

### 2. Base API Client (`src/api/client.py`)

Production-grade HTTP client with automatic retry logic:

```python
from src.api.client import BaseApiClient, ApiResponse, generate_request_id

# Generate unique request ID
req_id = generate_request_id()  # GS-20260703-000001

# Create client with custom settings
client = BaseApiClient(
    base_url="https://api.example.com",
    timeout=20.0,
    max_retries=5,
    backoff_factor=2.0
)

# Make request with automatic retries
response: ApiResponse = client.request(
    method="GET",
    endpoint="/data",
    params={"limit": 100}
)

if response.success:
    print(f"Status: {response.status_code}")
    print(f"Size: {response.response_size} bytes")
    print(f"Time: {response.execution_time_ms} ms")
    print(f"Checksum: {response.etag}")
else:
    print(f"Error: {response.error_message}")
```

**Features:**
- Automatic retry with exponential backoff
- Jitter to prevent thundering herd
- Custom User-Agent with version tracking
- Connection pooling via persistent sessions
- Timeout handling
- HTTP status code classification
- Response metadata extraction

### 3. Data Storage & File Operations (`src/utils/helpers.py`)

Atomic file operations with checksums:

```python
from src.utils.helpers import (
    generate_raw_storage_path,
    save_file_atomically,
    calculate_sha256
)
from pathlib import Path

# Generate storage path with automatic directory creation
storage_dir = generate_raw_storage_path("cea")
# Returns: Path to data/raw/cea/2026/07/03/ (created if missing)

# Save content atomically
file_path = storage_dir / "data.json"
checksum = save_file_atomically('{"key": "value"}', file_path)
# Returns: SHA-256 hash (also saved to file upon completion)

# Verify integrity later
recalc_checksum = calculate_sha256(file_path)
assert checksum == recalc_checksum  # Data integrity verified
```

**Guarantees:**
- Atomic writes (all-or-nothing via temp file + rename)
- No overwrites (new files only)
- SHA-256 checksums for integrity
- Auto-created directory hierarchies
- UTF-8 encoding for text files

### 4. Metadata & Audit Logging (`src/metadata.py`)

JSON Lines format metadata ledger:

```python
from src.metadata import (
    log_request_metadata,
    log_pipeline_summary,
    PipelineSummary,
    read_metadata_log,
    get_metadata_statistics
)

# Log individual request
log_request_metadata(
    source_name="cea",
    endpoint="/api/supply",
    request_id="GS-20260703-000001",
    status_code=200,
    success=True,
    execution_time_ms=245.5,
    response_size_bytes=15420,
    file_path=Path("data/raw/cea/2026/07/03/cea_...json"),
    sha256_checksum="a1b2c3...",
    headers=response_headers,
    content_type="application/json",
    row_count=150
)

# Log pipeline summary
summary = PipelineSummary(
    execution_start="2026-07-02T10:00:00+00:00",
    execution_end="2026-07-02T10:15:00+00:00",
    runtime_seconds=900.0,
    apis_attempted=8,
    successful_extractions=7,
    failed_extractions=1,
    total_rows_downloaded=125000,
    files_created=12,
    warnings_count=2,
    errors_count=1
)
log_pipeline_summary(summary)

# Query metadata later
stats = get_metadata_statistics(source_name="cea")
print(f"Total Requests: {stats['total_requests']}")
print(f"Success Rate: {stats['success_rate']}%")
```

---

## Installation & Setup

### Prerequisites
- Python 3.8+
- pip (Python package manager)
- Internet connection (for API calls)

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

**Key packages:**
- `requests>=2.31.0` - HTTP client
- `python-dotenv>=1.0.0` - Environment variable management
- `pyyaml>=6.0.1` - YAML parsing (future use)
- `pytest>=8.1.0` - Test framework
- `urllib3>=2.0.0` - Connection pooling

### Step 2: Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```ini
# System Settings
LOG_LEVEL=INFO
LOG_DIR=logs
RAW_DATA_DIR=data/raw

# API Settings
API_TIMEOUT_SEC=15
API_MAX_RETRIES=5
API_BACKOFF_FACTOR=2.0

# API Credentials
DATAGOV_API_KEY=your_api_key_here
WAQI_API_TOKEN=your_token_here
```

### Step 3: Verify Installation

Test imports and configuration:

```bash
python -c "from config.config import config; print(f'Config loaded: {config.raw_data_dir}')"
```

---

## Usage Examples

### Run Full Ingestion Pipeline

```bash
python run_ingest.py
```

Executes all 8 data sources in production mode.

### Run in Sample Mode

```bash
python run_ingest.py --sample
```

- Limits data to subset amounts (first state for geographic queries)
- Useful for testing without hitting rate limits
- Creates representative data files for testing downstream processes

### Run Specific Sources Only

```bash
python run_ingest.py --sources cea npp weather
```

Runs only CEA, NPP, and Weather sources.

### View Logs

```bash
tail -f logs/gridsense.log
```

Real-time log streaming with colored formatting.

### Query Metadata

```python
from src.metadata import read_metadata_log, get_metadata_statistics

# Get all CEA requests
cea_metadata = read_metadata_log(source_name="cea")
for record in cea_metadata:
    print(f"Request {record['request_id']}: {record['status_code']}")

# Get statistics
stats = get_metadata_statistics()
print(f"Total Requests: {stats['total_requests']}")
print(f"Success Rate: {stats['success_rate']}%")
print(f"Average Time: {stats['average_execution_time_ms']} ms")
```

---

## Configuration

All configuration is managed through `.env` file or environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_DIR` | logs | Directory for log files |
| `RAW_DATA_DIR` | data/raw | Directory for raw ingested data |
| `API_TIMEOUT_SEC` | 15 | HTTP request timeout in seconds |
| `API_MAX_RETRIES` | 5 | Maximum retry attempts on failure |
| `API_BACKOFF_FACTOR` | 2.0 | Exponential backoff multiplier |
| `DATAGOV_API_KEY` | (empty) | data.gov.in API key |
| `WAQI_API_TOKEN` | (empty) | WAQI API token |
| `DEFAULT_FILE_FORMAT` | json | Primary format (json, csv, xml) |
| `SUPPLEMENTARY_FORMATS` | csv,xml | Additional formats to save |

---

## API Clients

All API clients inherit from `BaseApiClient` and implement source-specific methods:

### CEA (Central Electricity Authority)
```python
from src.api.cea import CeaApiClient

client = CeaApiClient()
resp = client.get_daily_power_supply_position(limit=100)
resp = client.get_installed_capacity(limit=50)
```

### NPP (National Power Portal)
```python
from src.api.npp import NppApiClient

client = NppApiClient()
resp = client.get_daily_generation_by_plant()
resp = client.get_renewable_generation_summary()
```

### Open-Meteo (Weather)
```python
from src.api.open_meteo import OpenMeteoClient

client = OpenMeteoClient()
resp = client.get_weather_forecast(lat=18.9690, lon=72.8210)
resp = client.get_historical_weather(
    latitude=18.9690,
    longitude=72.8210,
    start_date="2026-06-28",
    end_date="2026-06-30"
)
```

### WAQI (Air Quality Index)
```python
from src.api.waqi import WaqiApiClient

client = WaqiApiClient()
resp = client.get_air_quality_by_coordinates(lat=18.9690, lon=72.8210)
resp = client.get_air_quality_by_city("Delhi")
```

### World Bank
```python
from src.api.world_bank import WorldBankApiClient

client = WorldBankApiClient()
# GDP indicator code: NY.GDP.MKTP.CD
resp = client.get_country_indicator("NY.GDP.MKTP.CD", start_year=2020, end_year=2024)
```

---

## Data Pipeline

### Storage Hierarchy

```
data/raw/
├── cea/
│   └── 2026/
│       └── 07/
│           └── 03/
│               ├── cea_2026-07-03T10-21-55Z_GS-20260703-000001.json
│               └── cea_2026-07-03T10-22-10Z_GS-20260703-000002.json
├── weather/
│   └── 2026/
│       └── 07/
│           └── 03/
│               ├── weather_2026-07-03T10-23-00Z_GS-20260703-000003.json
│               └── weather_2026-07-03T10-24-30Z_GS-20260703-000004.json
├── extraction_metadata.jsonl      # One record per request
└── pipeline_summaries.jsonl       # One record per pipeline run
```

### Metadata Record Format

```json
{
  "timestamp": "2026-07-03T10:21:55.123456+00:00",
  "source_name": "cea",
  "endpoint": "api-ingest",
  "request_id": "GS-20260703-000001",
  "status_code": 200,
  "success": true,
  "execution_time_ms": 245.5,
  "response_size_bytes": 15420,
  "file_path": "data/raw/cea/2026/07/03/cea_2026-07-03T10-21-55Z_GS-20260703-000001.json",
  "sha256_checksum": "a1b2c3d4e5f6g7h8...",
  "content_type": "application/json",
  "row_count": 150,
  "error_message": null,
  "response_headers": {
    "Server": "nginx/1.20.0",
    "Date": "Wed, 03 Jul 2026 10:21:55 GMT",
    "Cache-Control": "max-age=3600",
    "ETag": "W/\"12345\""
  }
}
```

### Pipeline Summary Record Format

```json
{
  "execution_start": "2026-07-03T10:00:00+00:00",
  "execution_end": "2026-07-03T10:45:30+00:00",
  "runtime_seconds": 2730.0,
  "apis_attempted": 8,
  "successful_extractions": 7,
  "failed_extractions": 1,
  "total_rows_downloaded": 425000,
  "files_created": 24,
  "warnings_count": 3,
  "errors_count": 1,
  "timestamp": "2026-07-03T10:45:30.987654+00:00"
}
```

---

## Testing

### Run Unit Tests

```bash
python -m pytest tests/test_client.py -v
python -m pytest tests/test_integration.py -v
```

### Run All Tests

```bash
python -m pytest tests/ -v --tb=short
```

### Test Coverage

```bash
pip install pytest-cov
pytest tests/ --cov=src --cov-report=html
```

---

## Quality Standards

### Code Standards
- ✅ PEP 8 compliant
- ✅ Type hints on all functions
- ✅ Comprehensive docstrings (Google style)
- ✅ No code duplication (DRY principle)
- ✅ SOLID principles applied

### Error Handling
- ✅ Graceful exception handling
- ✅ Detailed error logging
- ✅ Fallback to cached reference data
- ✅ Non-blocking API key validation

### Data Integrity
- ✅ SHA-256 checksums
- ✅ Atomic file writes
- ✅ Immutable storage (no overwrites)
- ✅ Comprehensive audit trail

### Performance
- ✅ Connection pooling
- ✅ Exponential backoff with jitter
- ✅ Configurable timeouts
- ✅ Efficient row estimation

---

## Troubleshooting

### Log Files Empty

**Symptom:** `logs/gridsense.log` not created

**Solution:**
```bash
chmod 755 logs/
python -c "from src.utils.logging_util import logger; logger.info('Test')"
```

### API Key Errors

**Symptom:** "Invalid API key" warnings

**Solution:**
1. Verify `.env` file exists and is readable
2. Check keys are correctly formatted (no extra spaces)
3. Verify keys haven't expired
4. For WAQI: Register at https://aqicn.org/api/

### Timeout Errors

**Solution:** Increase `API_TIMEOUT_SEC` in `.env`:
```ini
API_TIMEOUT_SEC=30
```

### Connection Refused

**Solution:** Check network connectivity:
```bash
ping api.data.gov.in
curl -I https://api.open-meteo.com
```

### File Permission Errors

**Solution:** Ensure write permissions:
```bash
chmod 755 data/
chmod 755 logs/
```

---

## Next Steps (Phase 4)

After completing Phase 3 ingestion:
- Build ETL transformation layer
- Create SQLite metadata database
- Implement DuckDB time-series storage
- Develop analytics dashboard
- Build machine learning models

---

## Support

For issues or questions:
1. Check logs: `tail -f logs/gridsense.log`
2. Review metadata: `head -20 data/raw/extraction_metadata.jsonl`
3. Verify configuration: `python -c "from config.config import config; print(config.__dict__)"`
4. Run in sample mode: `python run_ingest.py --sample`

---

**Last Updated:** July 2, 2026  
**Version:** Phase 3.0.0  
**Status:** Production Ready
