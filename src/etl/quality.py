"""Data quality reporting utilities for GridSense AI ETL."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.helpers import save_file_atomically


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class DataQualityReport:
    """Summary of dataset validation results."""

    dataset_name: str
    source_path: str
    file_format: str
    rows_read: int
    rows_valid: int
    rows_invalid: int
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    processing_time_seconds: float = 0.0
    created_at: str = field(default_factory=utc_now_iso)
    status: str = "UNKNOWN"
    report_path: Optional[str] = None
    staging_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a serializable representation of the report."""

        return asdict(self)


def calculate_quality_score(
    rows_read: int, rows_valid: int, errors: int, warnings: int
) -> float:
    """Calculate a simple data quality score on a 0-100 scale."""

    if rows_read <= 0:
        return 0.0

    validity_ratio = max(0.0, min(1.0, rows_valid / rows_read))
    penalty = min(50.0, errors * 8.0 + warnings * 2.0)
    score = (validity_ratio * 100.0) - penalty
    return round(max(0.0, min(100.0, score)), 2)


def write_quality_report(report: DataQualityReport, report_root: Path) -> Path:
    """Persist a quality report under reports/data_quality/."""

    safe_dataset = report.dataset_name.replace("/", "_").replace("\\", "_")
    target_dir = report_root / "data_quality" / safe_dataset
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    target_path = target_dir / filename
    payload = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    save_file_atomically(payload, target_path)
    return target_path
