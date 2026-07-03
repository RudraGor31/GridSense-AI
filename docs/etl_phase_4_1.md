# Phase 4.1 ETL Foundation & Validation

This document describes the ETL foundation implemented for GridSense AI Phase 4.1.

## Scope

- Raw-file discovery from `data/raw/`
- Parsing of JSON, CSV, and XML files
- Schema validation for tabular datasets
- Data quality reporting
- Resilient processing that continues after validation failures

## Exclusions

- Data cleaning
- Feature engineering
- SQLite loading
- DuckDB loading
- Analytics and dashboards
- Machine learning

## Outputs

- Validated staging datasets written to `data/processed/staging/`
- Quality reports written to `reports/data_quality/`

## Validation Rules

Supported checks include:

- Missing files
- Corrupted files
- Invalid JSON, CSV, or XML
- Missing required columns
- Incorrect data types
- Unexpected columns
- Duplicate records, detected only
- Empty datasets
- Invalid timestamps
- Invalid coordinates
- Negative values where impossible
