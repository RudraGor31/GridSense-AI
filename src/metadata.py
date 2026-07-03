"""Metadata Logging Module for GridSense AI.

This module captures execution details of individual API requests and persists
them in a local JSON Lines metadata ledger for auditability and data lineage.
It also manages pipeline-level summaries for execution statistics.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from config.config import config
from src.utils.logging_util import logger

# Paths to the shared metadata log files
METADATA_LOG_FILE = Path(config.raw_data_dir) / "extraction_metadata.jsonl"
PIPELINE_SUMMARY_FILE = Path(config.raw_data_dir) / "pipeline_summaries.jsonl"


def datetime_now_iso() -> str:
    """Helper returning current timestamp in ISO 8601 format.

    Returns:
        str: Current UTC timestamp in ISO 8601 format.
    """
    return datetime.now(timezone.utc).isoformat()


def log_request_metadata(
    source_name: str,
    endpoint: str,
    request_id: str,
    status_code: int,
    success: bool,
    execution_time_ms: float,
    response_size_bytes: int,
    file_path: Optional[Path],
    sha256_checksum: Optional[str],
    headers: Dict[str, str],
    content_type: str,
    error_message: Optional[str] = None,
    row_count: int = 0,
) -> None:
    """Logs the detailed metadata of a request to extraction_metadata.jsonl.

    Args:
        source_name: The name of the API source (e.g., 'cea').
        endpoint: The exact URL requested.
        request_id: Unique trace ID.
        status_code: HTTP status code.
        success: True if request was successful.
        execution_time_ms: Response time in milliseconds.
        response_size_bytes: Length of response content.
        file_path: Destination path of raw payload.
        sha256_checksum: SHA-256 checksum of saved file.
        headers: HTTP Response headers.
        content_type: MIME content type.
        error_message: Reason for failure (if any).
        row_count: Estimated rows in the dataset.
    """
    metadata_entry = {
        "timestamp": datetime_now_iso(),
        "source_name": source_name,
        "endpoint": endpoint,
        "request_id": request_id,
        "status_code": status_code,
        "success": success,
        "execution_time_ms": round(execution_time_ms, 2),
        "response_size_bytes": response_size_bytes,
        "file_path": str(file_path) if file_path else None,
        "sha256_checksum": sha256_checksum,
        "content_type": content_type,
        "row_count": row_count,
        "error_message": error_message,
        "response_headers": {
            "Server": headers.get("Server", ""),
            "Date": headers.get("Date", ""),
            "ETag": headers.get("ETag", ""),
            "Cache-Control": headers.get("Cache-Control", ""),
            "Content-Encoding": headers.get("Content-Encoding", ""),
        },
    }

    try:
        # Create directories if they do not exist
        METADATA_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Write to JSON Lines format (append mode)
        with open(METADATA_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(metadata_entry) + "\n")
        logger.debug(f"[{request_id}] Metadata recorded in {METADATA_LOG_FILE.name}")
    except Exception as e:
        logger.error(f"[{request_id}] Failed to write metadata log: {e}")


@dataclass
class PipelineSummary:
    """Summary statistics for a complete ingestion pipeline run."""

    execution_start: str
    execution_end: str
    runtime_seconds: float
    apis_attempted: int
    successful_extractions: int
    failed_extractions: int
    total_rows_downloaded: int
    files_created: int
    warnings_count: int
    errors_count: int
    timestamp: str = ""

    def __post_init__(self) -> None:
        """Auto-set timestamp if not provided."""
        if not self.timestamp:
            self.timestamp = datetime_now_iso()


def log_pipeline_summary(summary: PipelineSummary) -> None:
    """Logs the pipeline execution summary to pipeline_summaries.jsonl.

    Args:
        summary: PipelineSummary dataclass with execution statistics.
    """
    try:
        # Create directories if they do not exist
        PIPELINE_SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Convert dataclass to dictionary
        summary_dict = asdict(summary)

        # Write to JSON Lines format (append mode)
        with open(PIPELINE_SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary_dict) + "\n")

        logger.info(
            f"Pipeline summary recorded: {summary_dict['apis_attempted']} APIs, "
            f"{summary_dict['successful_extractions']} successful, "
            f"{summary_dict['failed_extractions']} failed, "
            f"{summary_dict['files_created']} files created"
        )
    except Exception as e:
        logger.error(f"Failed to write pipeline summary: {e}")


def read_metadata_log(source_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Reads and optionally filters metadata log entries.

    Args:
        source_name: Optional source name to filter results. None returns all entries.

    Returns:
        List of metadata log entries as dictionaries.
    """
    records: List[Dict[str, Any]] = []

    if not METADATA_LOG_FILE.exists():
        logger.warning(f"Metadata log file not found: {METADATA_LOG_FILE}")
        return records

    try:
        with open(METADATA_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    if source_name is None or record.get("source_name") == source_name:
                        records.append(record)
    except Exception as e:
        logger.error(f"Failed to read metadata log: {e}")

    return records


def read_pipeline_summaries() -> List[Dict[str, Any]]:
    """Reads all pipeline summary entries.

    Returns:
        List of pipeline summary entries as dictionaries.
    """
    records: List[Dict[str, Any]] = []

    if not PIPELINE_SUMMARY_FILE.exists():
        logger.warning(f"Pipeline summary file not found: {PIPELINE_SUMMARY_FILE}")
        return records

    try:
        with open(PIPELINE_SUMMARY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    records.append(record)
    except Exception as e:
        logger.error(f"Failed to read pipeline summaries: {e}")

    return records


def get_metadata_statistics(source_name: Optional[str] = None) -> Dict[str, Any]:
    """Calculates aggregated statistics from metadata logs.

    Args:
        source_name: Optional source name to filter statistics. None means all sources.

    Returns:
        Dictionary with aggregated statistics.
    """
    records = read_metadata_log(source_name)

    if not records:
        return {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "success_rate": 0.0,
            "total_response_size_bytes": 0,
            "average_execution_time_ms": 0.0,
        }

    successful = sum(1 for r in records if r.get("success", False))
    failed = len(records) - successful
    total_size = sum(r.get("response_size_bytes", 0) for r in records)
    avg_time = (
        sum(r.get("execution_time_ms", 0) for r in records) / len(records)
        if records
        else 0
    )

    return {
        "total_requests": len(records),
        "successful_requests": successful,
        "failed_requests": failed,
        "success_rate": round(successful / len(records) * 100, 2) if records else 0,
        "total_response_size_bytes": total_size,
        "average_execution_time_ms": round(avg_time, 2),
        "source_filter": source_name,
    }
