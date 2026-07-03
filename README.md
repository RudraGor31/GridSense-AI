# GridSense AI – Smart Energy Intelligence Platform

[![Python Tests](https://github.com/yourusername/GridSense-AI/actions/workflows/python-tests.yml/badge.svg)](https://github.com/yourusername/GridSense-AI/actions/workflows/python-tests.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## Phase 3: Production-Grade API Extraction & Ingestion Layer

A production-quality data extraction and API integration framework for **GridSense AI**. This platform ingests energy, meteorological, environmental, and demographic data across India's regional power grids and stores them in an immutable, auditable raw storage layer.

---

## Project Overview

GridSense AI is a comprehensive smart grid analytics platform designed to ingest real-time energy metrics, weather forecasts, environmental indices, demographic data, and macroeconomic indicators. This Phase 3 implementation provides a robust, production-ready extraction layer that:

- **Ingest from 8+ authoritative APIs** including CEA, NPP, Open-Meteo, WAQI, World Bank, Census, Holidays, and VAHAN
- **Ensure data integrity** through SHA-256 checksums and immutable storage partitioning
- **Enable request tracing** with unique request IDs used across logs, metadata, and audit trails
- **Provide resilience** via exponential backoff retry logic, connection pooling, and graceful fallbacks
- **Generate comprehensive logs** for pipeline auditing and debugging

## Project Motivation

Energy management is increasingly critical as India's power grid becomes more distributed and complex. Real-time visibility into energy supply, weather patterns, air quality, and vehicle electrification is essential for grid operators. This project enables:

1. **Data-Driven Grid Operations:** Collect and correlate energy metrics with environmental and demographic data
2. **Regulatory Compliance:** Maintain auditable records of all data ingestions with cryptographic checksums
3. **Scalable Foundation:** Build a production-grade API layer that can scale to additional data sources
4. **Operational Transparency:** Full request tracing and metadata logging for compliance and debugging

---

## Architecture Overview

The ingestion architecture employs **Single Responsibility Principle (SRP)** and **Immutable Storage** patterns to ensure reliability, auditability, and maintainability.

### Core Design Principles

- **API Client Decoupling:** Each data source is isolated in its own sub-module extending a common HTTP client base
- **Request Tracing:** Every HTTP execution receives a unique Request ID (format: `GS-YYYYMMDD-XXXXXX`)
- **Immutable File Storage:** All ingested files are stored as read-only snapshots partitioned by date with SHA-256 checksums
- **Resilient Failover:** Custom exponential backoff with jitter for rate-limiting (HTTP 429) and server errors (HTTP 5xx)
- **Comprehensive Metadata Logging:** Per-request and pipeline-level summaries in JSONL format for auditability

### Dependency Graph

```
                 [run_ingest.py]
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
   [src/api/*]                  [src/metadata.py]
   (cea, npp, open_meteo...)           │
         │                             │
         ▼                             ▼
   [src/api/client.py]        [extraction_metadata.jsonl]
         │
         ├─────────────────────────────┐
         ▼                             ▼
  [config/config.py]           [src/utils/helpers.py]
         │                             │
         ▼                             ▼
      [.env]                  [data/raw/{source}/YYYY/MM/DD/]
```

---

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Language** | Python | 3.12+ |
| **HTTP Client** | `requests` | ≥ 2.31.0 |
| **Configuration** | `python-dotenv` | ≥ 1.0.0 |
| **Data Format** | JSON/CSV | Native |
| **Cryptography** | `hashlib` (SHA-256) | Built-in |
| **Logging** | `logging` (Rotating Handlers) | Built-in |
| **Testing** | `pytest` | ≥ 8.1.0 |
| **Code Quality** | Black, Ruff, MyPy | Latest |
| **CI/CD** | GitHub Actions | Built-in |

---

## Folder Structure

```
GridSense-AI/
├── .github/
│   └── workflows/
│       └── python-tests.yml          # GitHub Actions CI workflow
├── config/
│   └── config.py                     # Configuration loader & validation
├── data/
│   ├── raw/                          # Immutable raw API responses
│   │   ├── cea/
│   │   ├── npp/
│   │   ├── weather/
│   │   ├── aqi/
│   │   ├── extraction_metadata.jsonl # Per-request metadata ledger
│   │   └── pipeline_summaries.jsonl  # Pipeline execution summaries
│   ├── processed/                    # Reserved for Phase 4 (ETL)
│   └── parquet/                      # Reserved for Phase 4 (Analytics)
├── database/
│   ├── sqlite/                       # Reserved for Phase 4 (SQLite)
│   └── duckdb/                       # Reserved for Phase 4 (DuckDB)
├── docs/
│   └── data_dictionary.md            # Data source specifications
├── logs/
│   └── gridsense.log                 # Rotating application logs
├── reports/                          # Reserved for Phase 4
├── src/
│   ├── api/
│   │   ├── __init__.py               # Exports all API clients
│   │   ├── client.py                 # Base HTTP client with retries/backoff
│   │   ├── cea.py                    # Central Electricity Authority
│   │   ├── npp.py                    # National Power Portal
│   │   ├── open_meteo.py             # Open-Meteo Weather API
│   │   ├── waqi.py                   # World Air Quality Index
│   │   ├── world_bank.py             # World Bank Indicators
│   │   ├── census.py                 # Indian Census Data
│   │   ├── holidays.py               # Nager.Date Holidays API
│   │   ├── data_gov.py               # data.gov.in Generic Resource
│   │   └── vahan.py                  # VAHAN EV Registration
│   ├── utils/
│   │   ├── helpers.py                # Path generation, checksums, atomic saves
│   │   └── logging_util.py           # Logger setup (console + rotating file)
│   ├── constants.py                  # Central constants & configuration
│   └── metadata.py                   # Metadata logging & pipeline tracking
├── tests/
│   ├── __init__.py
│   ├── test_client.py                # Base client unit tests
│   └── test_integration.py           # Integration & helper tests
├── run_ingest.py                     # Main orchestration script
├── requirements.txt                  # Python dependencies
├── .env.example                      # Environment variable template
├── LICENSE                           # Apache 2.0 License
├── README.md                         # This file
└── README_PHASE3.md                  # Detailed Phase 3 documentation
```

---

## Installation Guide

### Prerequisites

- **Python 3.12+** installed and added to system PATH
- **pip** package manager
- Active internet connection for API requests
- API credentials (free or registered) for data.gov.in, WAQI, etc.

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/GridSense-AI.git
cd GridSense-AI
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\Activate.ps1

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

Copy the example environment file:

```bash
# Windows
copy .env.example .env

# macOS/Linux
cp .env.example .env
```

Open `.env` and populate with your API credentials and settings.

---

## Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# API Credentials
DATAGOV_API_KEY=your_datagov_api_key_here
WAQI_API_TOKEN=your_waqi_token_here

# Application Settings
APP_ENV=development                    # development or production
LOG_LEVEL=INFO                        # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_DIR=logs/                         # Directory for application logs

# Request Settings
REQUEST_TIMEOUT=30                    # Seconds
MAX_RETRIES=3                         # Number of retry attempts
BACKOFF_FACTOR=2                      # Exponential backoff multiplier

# Data Storage
RAW_DATA_DIR=data/raw/                # Raw API response storage
PROCESSED_DATA_DIR=data/processed/    # Processed data (Phase 4)
PARQUET_DATA_DIR=data/parquet/        # Parquet files (Phase 4)
DATABASE_DIR=database/                # Database storage (Phase 4)
```

**Note:** Never commit actual credentials to version control. Use `.gitignore` to exclude `.env` files.

---

## How to Run

### Run Full Ingestion Pipeline

Execute the complete ingestion pipeline with all data sources:

```bash
python run_ingest.py
```

**Output:**
- Raw API responses saved to `data/raw/{source_name}/YYYY/MM/DD/`
- Metadata log appended to `data/raw/extraction_metadata.jsonl`
- Pipeline summary appended to `data/raw/pipeline_summaries.jsonl`
- Console and file logs written to `logs/gridsense.log`

### Run in Sample Mode

Sample mode limits data extraction to a subset of records (useful for testing without exhausting API quotas):

```bash
python run_ingest.py --sample
```

**Features:**
- Only fetches 5 records per source (vs. 100 in full mode)
- Weather queries limited to Mumbai instead of all state capitals
- AQI queries limited to Mumbai instead of all state capitals
- Useful for configuration testing and debugging

### Run Specific Sources

Extract data from only selected data sources:

```bash
# Extract only CEA and NPP data
python run_ingest.py --sources cea npp

# Extract only weather and AQI
python run_ingest.py --sources weather aqi

# Available sources: census, holidays, vahan, world_bank, cea, npp, weather, aqi
```

### Combine Sample Mode with Specific Sources

```bash
# Test CEA in sample mode
python run_ingest.py --sample --sources cea

# Test weather in sample mode
python run_ingest.py --sample --sources weather
```

---

## How to Execute API Extraction

The ingestion pipeline is orchestrated through `run_ingest.py`. Here's the execution flow:

1. **Initialization:** Load `.env` configuration and instantiate API clients
2. **Request Routing:** Route each data source to its specialized extractor
3. **Extraction:** Execute HTTP requests with retry logic and exponential backoff
4. **Storage:** Save raw responses atomically with SHA-256 checksum validation
5. **Metadata Tracking:** Log per-request metadata and pipeline-level statistics
6. **Error Handling:** Gracefully handle failures with fallback data generation

### Request Flow Diagram

```
User Command: python run_ingest.py
       │
       ├─→ Load Configuration (.env)
       ├─→ Create IngestionPipeline instance
       │
       ├─→ For each source (cea, npp, weather, aqi...):
       │   ├─→ Instantiate API Client
       │   ├─→ Execute API Request
       │   │   ├─→ Generate unique Request ID
       │   │   ├─→ Apply retry logic on 429/5xx
       │   │   └─→ Return ApiResponse
       │   ├─→ Save Raw Response
       │   │   ├─→ Write file atomically
       │   │   ├─→ Calculate SHA-256
       │   │   └─→ Partition by date/source
       │   └─→ Log Metadata
       │       └─→ Append to extraction_metadata.jsonl
       │
       └─→ Generate Pipeline Summary
           ├─→ Aggregate statistics
           ├─→ Calculate runtime
           └─→ Append to pipeline_summaries.jsonl
```

### Example Metadata Entry

```json
{
  "request_id": "GS-20260703-000001",
  "source_name": "cea",
  "endpoint": "api-ingest",
  "status_code": 200,
  "success": true,
  "execution_time_ms": 245.32,
  "response_size_bytes": 45823,
  "file_path": "data/raw/cea/2026/07/03/cea_2026-07-03T15:01:15Z_GS-20260703-000001.json",
  "sha256_checksum": "a7f8b9c3d2e1f0a9b8c7d6e5f4a3b2c1...",
  "content_type": "application/json",
  "headers": {...},
  "row_count": 42,
  "timestamp": "2026-07-03T15:01:15Z"
}
```

### Example Pipeline Summary

```json
{
  "execution_start": "2026-07-03T15:00:00Z",
  "execution_end": "2026-07-03T15:05:30Z",
  "runtime_seconds": 330.45,
  "apis_attempted": 8,
  "successful_extractions": 7,
  "failed_extractions": 1,
  "total_rows_downloaded": 1247,
  "files_created": 18,
  "warnings_count": 2,
  "errors_count": 1,
  "timestamp": "2026-07-03T15:05:30Z"
}
```

---

## How to Run Tests

### Run All Tests

Execute the complete test suite:

```bash
pytest
```

**Output:**
```
tests/test_client.py::TestBaseApiClient::test_request_id_generation PASSED
tests/test_client.py::TestBaseApiClient::test_exponential_backoff PASSED
tests/test_integration.py::TestAppConfig::test_config_initialization PASSED
... (more tests)

======================== 23 passed in 1.36s ========================
```

### Run Tests with Verbose Output

```bash
pytest -v
```

### Run Specific Test File

```bash
pytest tests/test_integration.py -v
```

### Run Specific Test Class

```bash
pytest tests/test_integration.py::TestAppConfig -v
```

### Run with Coverage Report

```bash
pytest --cov=src --cov-report=html
```

### Test Coverage

Current test coverage includes:
- **Base API Client:** Request ID generation, retry logic, timeout handling
- **Configuration:** Path validation, directory creation, environment loading
- **Utilities:** Timestamp formatting, SHA-256 checksums, atomic file saves
- **Metadata:** Request logging, pipeline summary tracking, JSONL parsing
- **Integration:** End-to-end extraction flow (mocked API responses)

---

## GitHub Actions Badge & CI/CD

The project includes automated CI/CD via GitHub Actions.

### Workflow: Python Tests

**File:** `.github/workflows/python-tests.yml`

**Triggers:**
- Every push to `main` or `develop` branches
- Every pull request to `main` or `develop` branches

**Jobs:**
1. **Setup:** Ubuntu latest, Python 3.12, pip cache
2. **Install:** Install dependencies from `requirements.txt`
3. **Test:** Run `pytest` with verbose output
4. **Report:** Display test summary and fail on errors

**Badge:**
```markdown
[![Python Tests](https://github.com/yourusername/GridSense-AI/actions/workflows/python-tests.yml/badge.svg)](https://github.com/yourusername/GridSense-AI/actions/workflows/python-tests.yml)
```

---

## Current Project Progress

### ✅ Phase 3 – API Extraction Layer (Complete)

**Completed:**
- [x] Production-quality HTTP client with exponential backoff and jitter
- [x] 8 specialized API client implementations
- [x] Immutable raw storage with date-based partitioning
- [x] SHA-256 checksum validation for data integrity
- [x] Atomic file writes to prevent partial data
- [x] Comprehensive metadata logging (JSONL)
- [x] Pipeline execution summaries
- [x] Request tracing with unique IDs (GS-YYYYMMDD-XXXXXX)
- [x] Configuration management with `.env` support
- [x] Type hints across all modules
- [x] Unit and integration tests (23/23 passing)
- [x] Code quality (Black, Ruff, MyPy)
- [x] GitHub Actions CI/CD workflow
- [x] Comprehensive documentation

**Test Results:**
```
======================== 23 passed in 1.36s ========================
- test_request_id_generation: PASSED
- test_exponential_backoff: PASSED
- test_api_response_structure: PASSED
- ... (20 more tests)
```

---

## Roadmap & Future Phases

### 🎯 Phase 4 – ETL & Data Warehousing (Planned)

- Transform raw JSON/CSV into standardized schemas
- Load into SQLite for transactional operations and DuckDB for analytics
- Implement data validation and quality checks
- Create aggregation pipelines for daily/weekly/monthly metrics

### 🎯 Phase 5 – Analytics & Dashboarding (Planned)

- Build interactive dashboards using Apache Superset or Grafana
- Real-time monitoring of grid metrics
- Anomaly detection and alerting
- Custom report generation

### 🎯 Phase 6 – Machine Learning (Planned)

- Predictive models for power demand forecasting
- Anomaly detection for grid faults
- Time-series forecasting for renewable energy
- Optimization models for grid operations

### 🎯 Phase 7 – Advanced Integrations (Planned)

- Real-time streaming via Apache Kafka
- Integration with grid control systems
- Mobile app for stakeholder notifications
- Blockchain-based audit trails

---

## License

This project is licensed under the **Apache License 2.0**. See [LICENSE](LICENSE) file for details.

You are free to:
- ✅ Use for commercial and private purposes
- ✅ Modify and distribute
- ✅ Include in larger projects

Provided you:
- 📋 Include a copy of the license
- 📝 State significant changes made
- ⚠️ Retain all copyright notices

---

## Contribution Guide

We welcome contributions! Here's how to get involved:

### 1. Fork the Repository

```bash
git clone https://github.com/yourusername/GridSense-AI.git
```

### 2. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 3. Make Your Changes

- Follow PEP 8 style guide
- Use type hints for all functions
- Write tests for new functionality
- Run `black`, `ruff`, and `mypy` before committing

### 4. Test Your Changes

```bash
pytest --cov=src
python -m black src/ tests/
python -m ruff check src/ tests/ --fix
python -m mypy src/ --explicit-package-bases --ignore-missing-imports
```

### 5. Commit with Clear Messages

```bash
git commit -m "feat: add new API integration for data source XYZ"
```

### 6. Push and Create a Pull Request

```bash
git push origin feature/your-feature-name
```

### Contribution Guidelines

- All tests must pass before merging
- Code must pass Black, Ruff, and MyPy checks
- New features require corresponding tests
- Documentation must be updated
- Pull requests must be reviewed before merging

---

## Acknowledgements

### Data Sources

- **Central Electricity Authority (CEA):** Power supply and demand data
- **National Power Portal (NPP):** Generation and capacity information
- **Open-Meteo:** Free weather forecasting API
- **World Air Quality Index (WAQI):** Air pollution measurements
- **World Bank:** Macroeconomic indicators
- **National Census Commissioner:** Demographic data
- **Nager.Date:** Indian holiday calendar
- **VAHAN:** Vehicle registration data (EV statistics)

### Libraries & Tools

- **Requests:** HTTP client library
- **Python-DotEnv:** Environment variable management
- **Pytest:** Testing framework
- **Black:** Code formatter
- **Ruff:** Python linter
- **MyPy:** Static type checker
- **GitHub Actions:** CI/CD automation

### Contributors

Special thanks to all contributors and community members who have helped improve this project.

---

## Support & Contact

For questions, issues, or suggestions:

- 📧 **Email:** support@gridsense-ai.com
- 🐛 **Issues:** [GitHub Issues](https://github.com/yourusername/GridSense-AI/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/yourusername/GridSense-AI/discussions)

---

**Last Updated:** July 3, 2026  
**Status:** ✅ Phase 3 Complete – Production Ready  
**Version:** 3.0.0  
**Maintainers:** GridSense AI Team
