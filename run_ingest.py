"""GridSense AI Daily Ingestion Orchestrator.

This script executes the Phase 3 data extraction layer, fetching raw metrics
from all approved APIs, saving the raw data, and logging metadata summaries.
"""

import argparse
import sys
import time
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.config import config
from src.utils.logging_util import logger
from src.utils.helpers import (
    generate_raw_storage_path,
    save_file_atomically,
    get_current_utc_timestamp,
)
from src.metadata import log_request_metadata, log_pipeline_summary, PipelineSummary

# Import API Clients
from src.api import (
    CeaApiClient,
    NppApiClient,
    OpenMeteoClient,
    WaqiApiClient,
    WorldBankApiClient,
    CensusDataExtractor,
    HolidaysApiClient,
    VahanEvExtractor,
    ApiResponse,
)

# Standard geographical coordinates for key state capital hubs in India
STATE_CAPITALS = {
    "Maharashtra": {"capital": "Mumbai", "lat": 18.9690, "lon": 72.8210},
    "Uttar Pradesh": {"capital": "Lucknow", "lat": 26.8467, "lon": 80.9462},
    "Tamil Nadu": {"capital": "Chennai", "lat": 13.0827, "lon": 80.2707},
    "West Bengal": {"capital": "Kolkata", "lat": 22.5726, "lon": 88.3639},
    "Gujarat": {"capital": "Gandhinagar", "lat": 23.2156, "lon": 72.6369},
    "Assam": {"capital": "Guwahati", "lat": 26.1445, "lon": 91.7362},
}


class IngestionPipeline:
    """Manages the lifecycle of an ingestion run across all data sources."""

    def __init__(self, sample_mode: bool = False) -> None:
        """Initializes the ingestion pipeline.

        Args:
            sample_mode: If True, limits data extraction to sample/subset amounts.
        """
        self.sample_mode = sample_mode
        self.summary_file = Path(config.raw_data_dir) / "pipeline_summaries.jsonl"

        # Instantiate API clients
        self.cea_client = CeaApiClient()
        self.npp_client = NppApiClient()
        self.weather_client = OpenMeteoClient()
        self.waqi_client = WaqiApiClient()
        self.wb_client = WorldBankApiClient()
        self.census_extractor = CensusDataExtractor()
        self.holiday_client = HolidaysApiClient()
        self.vahan_extractor = VahanEvExtractor()

    def run(self, specific_sources: Optional[List[str]] = None) -> None:
        """Runs the extraction pipeline.

        Args:
            specific_sources: Optional filter list to ingest only target sources.
        """
        start_time = time.perf_counter()
        start_timestamp = datetime.now(timezone.utc).isoformat()

        # Pipeline State
        apis_attempted = 0
        apis_successful = 0
        apis_failed = 0
        total_rows = 0
        files_created = 0
        warnings = 0
        errors = 0

        logger.info(
            f"GridSense AI Ingestion Pipeline started. Mode: {'Sample' if self.sample_mode else 'Full'}"
        )

        # List of all available extraction routines
        sources: Dict[str, Any] = {
            "census": self._ingest_census,
            "holidays": self._ingest_holidays,
            "vahan": self._ingest_vahan,
            "world_bank": self._ingest_world_bank,
            "cea": self._ingest_cea,
            "npp": self._ingest_npp,
            "weather": self._ingest_weather,
            "aqi": self._ingest_aqi,
        }

        # Filter sources if requested
        active_sources = specific_sources if specific_sources else list(sources.keys())

        for name in active_sources:
            if name not in sources:
                logger.warning(f"Unknown source request ignored: {name}")
                warnings += 1
                continue

            apis_attempted += 1
            logger.info(f"Ingestion worker starting source: {name}")
            try:
                # Execute specific ingestion task
                run_stats = sources[name]()

                files_created += run_stats["files_created"]
                total_rows += run_stats["rows"]

                if run_stats["failed"] == 0:
                    apis_successful += 1
                    logger.info(f"Source Ingestion successful: {name}")
                else:
                    apis_failed += 1
                    errors += run_stats["failed"]
                    logger.error(
                        f"Source Ingestion completed with partial failures: {name}"
                    )

            except Exception as e:
                apis_failed += 1
                errors += 1
                logger.error(
                    f"Critical unhandled error in source ingestion '{name}': {e}",
                    exc_info=True,
                )

        # Ingestion metrics aggregation
        end_time = time.perf_counter()
        end_timestamp = datetime.now(timezone.utc).isoformat()
        runtime_sec = end_time - start_time

        # Create pipeline summary using the dataclass
        pipeline_summary = PipelineSummary(
            execution_start=start_timestamp,
            execution_end=end_timestamp,
            runtime_seconds=round(runtime_sec, 2),
            apis_attempted=apis_attempted,
            successful_extractions=apis_successful,
            failed_extractions=apis_failed,
            total_rows_downloaded=total_rows,
            files_created=files_created,
            warnings_count=warnings,
            errors_count=errors,
        )

        # Log the pipeline summary
        log_pipeline_summary(pipeline_summary)

        # Also print summary report
        self._print_summary_report(pipeline_summary)

    def _print_summary_report(self, summary: PipelineSummary) -> None:
        """Outputs a clean report summary to stdout."""
        border = "=" * 70
        report = f"""
{border}
GRID SENSE AI - INGESTION PIPELINE RUN SUMMARY
{border}
Execution Start:    {summary.execution_start}
Execution End:      {summary.execution_end}
Total Runtime:      {summary.runtime_seconds} seconds
APIs Attempted:     {summary.apis_attempted}
Successful APIs:    {summary.successful_extractions}
Failed APIs:        {summary.failed_extractions}
Total Rows Raw:     {summary.total_rows_downloaded}
Files Created:      {summary.files_created}
Warnings:           {summary.warnings_count}
Errors/Failures:    {summary.errors_count}
Timestamp:          {summary.timestamp}
{border}
"""
        logger.info(report)
        print(report)

    # Ingestion tasks helpers
    def _save_raw_response(
        self, source_name: str, response: ApiResponse, extension: str = "json"
    ) -> Dict[str, Any]:
        """Saves a response to raw storage and writes trace metadata logs.

        Args:
            source_name: Name of the data source.
            response: The ApiResponse object from the API client.
            extension: File extension for the saved file (json, csv, xml).

        Returns:
            Dictionary with extraction statistics.
        """
        result: Dict[str, Any] = {"files_created": 0, "rows": 0, "failed": 0}

        if not response.success:
            log_request_metadata(
                source_name=source_name,
                endpoint="unknown",
                request_id=response.request_id,
                status_code=response.status_code,
                success=False,
                execution_time_ms=response.execution_time_ms,
                response_size_bytes=response.response_size,
                file_path=None,
                sha256_checksum=None,
                headers=response.headers,
                content_type=response.content_type,
                error_message=response.error_message,
            )
            result["failed"] = 1
            return result

        # Validate basic properties
        if not response.text or response.response_size == 0:
            logger.warning(
                f"[{response.request_id}] Empty payload returned for source: {source_name}"
            )
            result["failed"] = 1
            return result

        # Save payload
        target_dir = generate_raw_storage_path(source_name)
        timestamp = get_current_utc_timestamp()
        filename = f"{source_name}_{timestamp}_{response.request_id}.{extension}"
        file_path = target_dir / filename

        try:
            checksum = save_file_atomically(response.text, file_path)
            result["files_created"] = 1

            # Simple row count estimation based on payload structure
            row_count = self._estimate_rows(response.text, extension)
            result["rows"] = row_count

            # Log metadata success
            log_request_metadata(
                source_name=source_name,
                endpoint="api-ingest",
                request_id=response.request_id,
                status_code=response.status_code,
                success=True,
                execution_time_ms=response.execution_time_ms,
                response_size_bytes=response.response_size,
                file_path=file_path,
                sha256_checksum=checksum,
                headers=response.headers,
                content_type=response.content_type,
                row_count=row_count,
            )
            logger.debug(f"[{response.request_id}] Saved {source_name} to {file_path}")
        except Exception as e:
            logger.error(
                f"[{response.request_id}] Failed to save raw storage file: {e}"
            )
            result["failed"] = 1

        return result

    @staticmethod
    def _estimate_rows(raw_text: str, extension: str) -> int:
        """Estimates the row counts inside the raw file without schema cleaning.

        Args:
            raw_text: The raw text content of the response.
            extension: File format (json, csv, xml).

        Returns:
            Estimated row count in the data.
        """
        if extension == "json":
            try:
                data = json.loads(raw_text)
                if isinstance(data, list):
                    return len(data)
                if isinstance(data, dict):
                    # Check common JSON data keys
                    for key in ["records", "data", "results", "hourly"]:
                        if key in data and isinstance(data[key], (list, dict)):
                            if isinstance(data[key], list):
                                return len(data[key])
                            if isinstance(data[key], dict):
                                # If it's a dictionary of equal length lists (Open-Meteo style)
                                first_val = next(iter(data[key].values()), None)
                                if isinstance(first_val, list):
                                    return len(first_val)
                                return len(data[key])
                    return 1
            except Exception:
                return 0
        elif extension in ["csv", "xml"]:
            # Basic fallback counts based on line carriage splits
            return max(0, len(raw_text.splitlines()) - 1)
        return 0

    # ========================================================================
    # Ingestion implementations by data source
    # ========================================================================

    def _ingest_census(self) -> Dict[str, Any]:
        """Ingests demographic and population data from Census datasets."""
        resp = self.census_extractor.extract_demographics()
        return self._save_raw_response("census", resp)

    def _ingest_holidays(self) -> Dict[str, Any]:
        """Ingests public holiday calendar for India."""
        resp = self.holiday_client.get_holidays()
        return self._save_raw_response("holidays", resp)

    def _ingest_vahan(self) -> Dict[str, Any]:
        """Ingests electric vehicle registration statistics."""
        resp = self.vahan_extractor.get_ev_registrations()
        return self._save_raw_response("vahan", resp)

    def _ingest_world_bank(self) -> Dict[str, Any]:
        """Ingests macroeconomic indicators from World Bank API."""
        # GDP code (NY.GDP.MKTP.CD)
        resp = self.wb_client.get_country_indicator(
            "NY.GDP.MKTP.CD", start_year=2020, end_year=2024
        )
        return self._save_raw_response("world_bank", resp)

    def _ingest_cea(self) -> Dict[str, Any]:
        """Ingests power supply position from CEA."""
        # If in sample mode, fetch only a few records
        limit = 5 if self.sample_mode else 100
        resp = self.cea_client.get_daily_power_supply_position(limit=limit)
        return self._save_raw_response("cea", resp)

    def _ingest_npp(self) -> Dict[str, Any]:
        """Ingests plant-level generation data from NPP."""
        limit = 5 if self.sample_mode else 100
        resp = self.npp_client.get_daily_generation_by_plant(limit=limit)
        return self._save_raw_response("npp", resp)

    def _ingest_weather(self) -> Dict[str, Any]:
        """Ingests forecast and historical weather profiles for state capitals."""
        files_created = 0
        rows = 0
        failed = 0

        # Weather pulls are coordinate based. Loop through STATE_CAPITALS.
        for state, details in STATE_CAPITALS.items():
            # In sample mode, only query the first state (Maharashtra/Mumbai) to save requests
            if self.sample_mode and state != "Maharashtra":
                continue

            logger.info(
                f"Ingesting weather forecast for {details['capital']} ({state})"
            )

            # Forecast Ingest
            fcst_resp = self.weather_client.get_weather_forecast(
                details["lat"], details["lon"]
            )
            fcst_stats = self._save_raw_response("weather", fcst_resp)

            files_created += fcst_stats["files_created"]
            rows += fcst_stats["rows"]
            failed += fcst_stats["failed"]

            # Historical Actual Ingest (Fetch past 3 days for model continuous updates)
            # Use mock actual date range for pipeline validation
            logger.info(f"Ingesting weather actuals for {details['capital']} ({state})")
            hist_resp = self.weather_client.get_historical_weather(
                latitude=details["lat"],
                longitude=details["lon"],
                start_date="2026-06-28",
                end_date="2026-06-30",
            )
            hist_stats = self._save_raw_response("weather", hist_resp)

            files_created += hist_stats["files_created"]
            rows += hist_stats["rows"]
            failed += hist_stats["failed"]

        return {"files_created": files_created, "rows": rows, "failed": failed}

    def _ingest_aqi(self) -> Dict[str, Any]:
        """Ingests real-time AQI ratings for state capitals."""
        files_created = 0
        rows = 0
        failed = 0

        for state, details in STATE_CAPITALS.items():
            if self.sample_mode and state != "Maharashtra":
                continue

            logger.info(f"Ingesting AQI metrics for {details['capital']} ({state})")
            resp = self.waqi_client.get_air_quality_by_coordinates(
                details["lat"], details["lon"]
            )
            stats = self._save_raw_response("aqi", resp)

            files_created += stats["files_created"]
            rows += stats["rows"]
            failed += stats["failed"]

        return {"files_created": files_created, "rows": rows, "failed": failed}


def main() -> None:
    """Main entry point for the ingestion orchestrator."""
    parser = argparse.ArgumentParser(
        description="GridSense AI Data Extraction Execution Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_ingest.py                        # Run all sources in full mode
  python run_ingest.py --sample               # Run all sources in sample mode (limited data)
  python run_ingest.py --sources cea npp      # Run only CEA and NPP sources
  python run_ingest.py --sample --sources cea # Run only CEA in sample mode
        """,
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Execute run in Sample/Mock Mode targeting a subset of records to test interface endpoints.",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        help="Space-separated source names to run (e.g., --sources cea npp weather)",
    )
    args = parser.parse_args()

    pipeline = IngestionPipeline(sample_mode=args.sample)

    try:
        pipeline.run(specific_sources=args.sources)
    except KeyboardInterrupt:
        logger.error("Ingestion run aborted manually by operator interrupt.")
        sys.exit(1)
    except Exception as error:
        logger.error(
            f"Ingestion run aborted due to system failure: {error}", exc_info=True
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
