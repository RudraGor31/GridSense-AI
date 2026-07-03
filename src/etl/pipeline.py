"""Reusable ETL pipeline for validated staging datasets."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config.config import config
from src.etl.exceptions import ETLStageError, ETLValidationError
from src.etl.extract import discover_raw_files, load_raw_dataset
from src.etl.quality import DataQualityReport, write_quality_report
from src.etl.schema_validator import ColumnRule, SchemaDefinition
from src.etl.validate import ValidationOutcome, ValidationService
from src.utils.helpers import save_file_atomically
from src.utils.logging_util import logger


@dataclass(slots=True)
class ETLRunResult:
    """Summary for a complete ETL run."""

    datasets_processed: int = 0
    datasets_validated: int = 0
    datasets_failed: int = 0
    staging_files_written: int = 0
    quality_reports_written: int = 0
    processing_time_seconds: float = 0.0
    dataset_results: List[Dict[str, Any]] = field(default_factory=list)


DEFAULT_SCHEMAS: Dict[str, SchemaDefinition] = {
    "cea": SchemaDefinition(
        name="cea",
        columns={
            "timestamp": ColumnRule(
                name="timestamp", data_type="timestamp", required=True
            ),
            "state": ColumnRule(name="state", data_type="string", required=True),
            "demand_mw": ColumnRule(
                name="demand_mw",
                data_type="number",
                required=True,
                allow_negative=False,
            ),
            "supply_mw": ColumnRule(
                name="supply_mw",
                data_type="number",
                required=False,
                allow_negative=False,
            ),
        },
        allow_extra_columns=True,
    ),
    "weather": SchemaDefinition(
        name="weather",
        columns={
            "timestamp": ColumnRule(
                name="timestamp", data_type="timestamp", required=True
            ),
            "latitude": ColumnRule(
                name="latitude",
                data_type="number",
                required=True,
                allow_negative=False,
                minimum=-90.0,
                maximum=90.0,
            ),
            "longitude": ColumnRule(
                name="longitude",
                data_type="number",
                required=True,
                allow_negative=False,
                minimum=-180.0,
                maximum=180.0,
            ),
            "temperature_c": ColumnRule(
                name="temperature_c", data_type="number", required=False
            ),
        },
        allow_extra_columns=True,
    ),
    "aqi": SchemaDefinition(
        name="aqi",
        columns={
            "timestamp": ColumnRule(
                name="timestamp", data_type="timestamp", required=True
            ),
            "latitude": ColumnRule(
                name="latitude",
                data_type="number",
                required=True,
                minimum=-90.0,
                maximum=90.0,
            ),
            "longitude": ColumnRule(
                name="longitude",
                data_type="number",
                required=True,
                minimum=-180.0,
                maximum=180.0,
            ),
            "aqi": ColumnRule(
                name="aqi", data_type="integer", required=False, allow_negative=False
            ),
        },
        allow_extra_columns=True,
    ),
}


class ETLPipeline:
    """Coordinate raw extraction, validation, and staging writes."""

    def __init__(
        self,
        raw_root: Optional[Path] = None,
        processed_root: Optional[Path] = None,
        reports_root: Optional[Path] = None,
        schema_registry: Optional[Dict[str, SchemaDefinition]] = None,
        validation_service: Optional[ValidationService] = None,
    ) -> None:
        self.raw_root = raw_root or Path(config.raw_data_dir)
        self.processed_root = processed_root or Path(config.processed_data_dir)
        self.reports_root = reports_root or Path(config.reports_dir)
        self.schema_registry = schema_registry or DEFAULT_SCHEMAS
        self.validation_service = validation_service or ValidationService()

        self.staging_root = self.processed_root / "staging"
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.reports_root.mkdir(parents=True, exist_ok=True)

    def run(self, dataset_filter: Optional[Iterable[str]] = None) -> ETLRunResult:
        """Run the ETL foundation over all discovered raw datasets."""

        start_time = time.perf_counter()
        result = ETLRunResult()

        for file_path in discover_raw_files(
            self.raw_root, dataset_filter=dataset_filter
        ):
            result.datasets_processed += 1
            dataset_name = self._infer_dataset_name(file_path)
            stage_start = time.perf_counter()

            try:
                raw_dataset = load_raw_dataset(file_path, dataset_name=dataset_name)
                schema = self.schema_registry.get(dataset_name)
                if schema is None:
                    schema = self._fallback_schema(dataset_name)

                validation = self.validation_service.validate(
                    dataset_name=raw_dataset.dataset_name,
                    records=raw_dataset.records,
                    source_path=raw_dataset.source_path,
                    file_format=raw_dataset.file_format,
                    schema=schema,
                    processing_time_seconds=time.perf_counter() - stage_start,
                )

                self._persist_quality_report(validation.report)
                result.quality_reports_written += 1

                if validation.report and validation.report.rows_valid > 0:
                    staging_path = self._write_staging_dataset(validation)
                    validation.report.staging_path = str(staging_path)
                    result.staging_files_written += 1

                result.datasets_validated += 1
                result.dataset_results.append(self._result_to_dict(validation))

            except (ETLValidationError, ETLStageError) as exc:
                result.datasets_failed += 1
                logger.error(
                    "ETL dataset failure | dataset=%s | file=%s | error=%s",
                    dataset_name,
                    file_path,
                    exc,
                )
                result.dataset_results.append(
                    {
                        "dataset_name": dataset_name,
                        "source_path": str(file_path),
                        "status": "FAILED",
                        "error": str(exc),
                    }
                )
            except (
                Exception
            ) as exc:  # pragma: no cover - defensive guard for unexpected runtime failures
                result.datasets_failed += 1
                logger.exception(
                    "Unexpected ETL failure for dataset=%s | file=%s",
                    dataset_name,
                    file_path,
                )
                result.dataset_results.append(
                    {
                        "dataset_name": dataset_name,
                        "source_path": str(file_path),
                        "status": "FAILED",
                        "error": str(exc),
                    }
                )

        result.processing_time_seconds = round(time.perf_counter() - start_time, 4)
        return result

    def _persist_quality_report(self, report: Optional[DataQualityReport]) -> None:
        if report is None:
            return
        report_path = write_quality_report(report, self.reports_root)
        report.report_path = str(report_path)

    def _write_staging_dataset(self, validation: ValidationOutcome) -> Path:
        staging_dir = self.staging_root / validation.dataset_name
        staging_dir.mkdir(parents=True, exist_ok=True)
        staging_file = staging_dir / f"{Path(validation.source_path).stem}.jsonl"
        payload = "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in validation.validated_records
        )
        save_file_atomically(payload, staging_file)
        return staging_file

    @staticmethod
    def _infer_dataset_name(file_path: Path) -> str:
        parents = list(file_path.parents)
        for index, parent in enumerate(parents):
            if parent.name.lower() == "raw" and index > 0:
                return parents[index - 1].name.lower()

        return (
            file_path.parent.name.lower()
            if file_path.parent.name
            else file_path.stem.lower()
        )

    @staticmethod
    def _fallback_schema(dataset_name: str) -> SchemaDefinition:
        return SchemaDefinition(name=dataset_name, columns={}, allow_extra_columns=True)

    @staticmethod
    def _result_to_dict(validation: ValidationOutcome) -> Dict[str, Any]:
        report = validation.report.to_dict() if validation.report else None
        return {
            "dataset_name": validation.dataset_name,
            "source_path": str(validation.source_path),
            "file_format": validation.file_format,
            "rows_read": len(validation.records),
            "rows_valid": len(validation.validated_records),
            "rows_invalid": len(validation.invalid_records),
            "status": report["status"] if report else "UNKNOWN",
            "quality_score": report["quality_score"] if report else 0.0,
            "warnings": validation.warnings,
            "errors": validation.errors,
            "report_path": report.get("report_path") if report else None,
            "staging_path": report.get("staging_path") if report else None,
        }
