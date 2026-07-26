"""Cleaning audit trail utilities for Phase 4.2.

Every cleaning operation performed by the GridSense AI ETL engine is recorded
as an :class:`AuditRecord`.  Records are written atomically to
``reports/cleaning/audit/<dataset>/`` for full traceability and reproducibility.

Design principles
-----------------
- Immutable records once written (append-only JSONL files).
- Every record carries a monotonic UTC timestamp and a unique request ID so
  that audit files can be correlated with pipeline logs.
- :func:`compute_cleaning_score` produces a deterministic 0-100 quality score
  derived from retention ratio, error count, and warning count.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from src.api.client import generate_request_id
from src.utils.helpers import save_file_atomically


def now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string.

    Returns
    -------
    str
        e.g. ``"2026-07-06T11:00:00+00:00"``
    """
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class AuditRecord:
    """Single cleaning change audit record.

    Attributes
    ----------
    dataset:
        Name of the dataset being cleaned (e.g. ``"weather"``).
    column:
        Column that was modified, or ``"<row>"`` for row-level operations.
    original_value:
        Value before the cleaning rule was applied.
    new_value:
        Value after the cleaning rule was applied (or a sentinel string such
        as ``"<ROW_DROPPED>"``).
    cleaning_rule:
        Slug identifying the rule (e.g. ``"missing_mean"``, ``"dtype_float"``).
    timestamp:
        UTC ISO-8601 timestamp when the record was created.
    request_id:
        Unique ID correlating this record to a pipeline execution.
    row_index:
        Zero-based index of the affected row; ``-1`` means unknown/batch.
    """

    dataset: str
    column: str
    original_value: Any
    new_value: Any
    cleaning_rule: str
    timestamp: str = field(default_factory=now_iso)
    request_id: str = field(default_factory=generate_request_id)
    row_index: int = -1


@dataclass(slots=True)
class CleaningSummary:
    """Summary report for one dataset cleaning run.

    Attributes
    ----------
    dataset:
        Name of the dataset.
    rows_before:
        Row count before cleaning.
    rows_after:
        Row count after cleaning (rows may be dropped by missing/duplicate rules).
    missing_values_fixed:
        Total number of missing-value cells that were filled or row-dropped.
    duplicates_removed:
        Number of duplicate rows removed.
    columns_renamed:
        Number of column names that were normalised to snake_case.
    data_types_corrected:
        Number of cell values that were cast to the target type.
    outliers_flagged:
        Number of cells flagged as outliers (never removed automatically).
    execution_time_seconds:
        Wall-clock time for the cleaning pass.
    cleaning_score:
        0-100 composite quality score computed by :func:`compute_cleaning_score`.
    warnings:
        Non-fatal issues encountered during cleaning.
    errors:
        Fatal or near-fatal issues encountered during cleaning.
    created_at:
        UTC ISO-8601 timestamp when the summary was generated.
    request_id:
        Unique ID for this pipeline run.
    """

    dataset: str
    rows_before: int
    rows_after: int
    missing_values_fixed: int = 0
    duplicates_removed: int = 0
    columns_renamed: int = 0
    data_types_corrected: int = 0
    outliers_flagged: int = 0
    execution_time_seconds: float = 0.0
    cleaning_score: float = 0.0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    request_id: str = field(default_factory=generate_request_id)


def write_audit_log(
    records: List[AuditRecord],
    reports_root: Path,
    dataset_name: str,
) -> Path:
    """Write audit records atomically to ``reports/cleaning/audit/<dataset>/``.

    Each invocation creates a new timestamped JSONL file so that repeated runs
    produce separate, non-overlapping audit files.

    Parameters
    ----------
    records:
        List of :class:`AuditRecord` instances produced during the cleaning run.
    reports_root:
        Root directory for all reports (e.g. ``Path("reports")``).
    dataset_name:
        Dataset identifier used as a sub-directory name.

    Returns
    -------
    Path
        Absolute path to the written audit file.
    """
    target_dir = reports_root / "cleaning" / "audit" / dataset_name
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = (
        target_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    )
    payload = "\n".join(
        json.dumps(asdict(record), ensure_ascii=False) for record in records
    )
    save_file_atomically(payload, file_path)
    return file_path


def write_cleaning_summary(summary: CleaningSummary, reports_root: Path) -> Path:
    """Write a cleaning summary report to ``reports/cleaning/``.

    Parameters
    ----------
    summary:
        Populated :class:`CleaningSummary` dataclass.
    reports_root:
        Root directory for all reports.

    Returns
    -------
    Path
        Absolute path to the written summary JSON file.
    """
    target_dir = reports_root / "cleaning"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = (
        target_dir
        / f"{summary.dataset}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    payload = json.dumps(asdict(summary), indent=2, ensure_ascii=False)
    save_file_atomically(payload, file_path)
    return file_path


def compute_cleaning_score(summary: CleaningSummary) -> float:
    """Compute a composite 0-100 cleaning quality score.

    Algorithm
    ---------
    The score starts at 100 × (rows_after / rows_before) to reward high data
    retention, then subtracts penalties for errors (−10 each) and warnings
    (−3 each).  The result is clamped to [0.0, 100.0].

    Parameters
    ----------
    summary:
        Partially populated summary (``cleaning_score`` is ignored as an input).

    Returns
    -------
    float
        Score in the range [0.0, 100.0] rounded to two decimal places.
    """
    if summary.rows_before <= 0:
        return 0.0

    retention_ratio = max(0.0, min(1.0, summary.rows_after / summary.rows_before))
    penalty = (len(summary.errors) * 10.0) + (len(summary.warnings) * 3.0)
    score = (retention_ratio * 100.0) - penalty
    return round(max(0.0, min(100.0, score)), 2)
