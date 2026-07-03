"""Validation orchestration for GridSense AI ETL."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.etl.exceptions import ETLValidationError
from src.etl.quality import DataQualityReport, calculate_quality_score
from src.etl.schema_validator import (
    SchemaDefinition,
    SchemaValidationResult,
    SchemaValidator,
)
from src.utils.logging_util import logger


@dataclass(slots=True)
class ValidationOutcome:
    """Combined validation outcome for a dataset."""

    dataset_name: str
    source_path: Path
    file_format: str
    records: List[Dict[str, Any]]
    validated_records: List[Dict[str, Any]]
    invalid_records: List[Dict[str, Any]] = field(default_factory=list)
    schema_result: Optional[SchemaValidationResult] = None
    report: Optional[DataQualityReport] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ValidationService:
    """Orchestrates schema validation and data quality reporting."""

    def __init__(self, schema_validator: Optional[SchemaValidator] = None) -> None:
        self.schema_validator = schema_validator or SchemaValidator()

    def validate(
        self,
        dataset_name: str,
        records: Sequence[Dict[str, Any]],
        source_path: Path,
        file_format: str,
        schema: Optional[SchemaDefinition] = None,
        processing_time_seconds: float = 0.0,
    ) -> ValidationOutcome:
        """Validate a parsed dataset and build a quality report."""

        if schema is None:
            raise ETLValidationError(
                f"No schema registered for dataset '{dataset_name}'."
            )

        schema_result = self.schema_validator.validate(records, schema)
        valid_indices = set(range(schema_result.rows_checked)) - set(
            schema_result.invalid_row_indices
        )
        validated_records = [
            record for index, record in enumerate(records) if index in valid_indices
        ]
        invalid_records = [
            record for index, record in enumerate(records) if index not in valid_indices
        ]

        quality_report = DataQualityReport(
            dataset_name=dataset_name,
            source_path=str(source_path),
            file_format=file_format,
            rows_read=schema_result.rows_checked,
            rows_valid=schema_result.valid_rows,
            rows_invalid=schema_result.invalid_rows,
            validation_errors=schema_result.errors.copy(),
            warnings=schema_result.warnings.copy(),
            quality_score=calculate_quality_score(
                schema_result.rows_checked,
                schema_result.valid_rows,
                len(schema_result.errors),
                len(schema_result.warnings),
            ),
            processing_time_seconds=round(processing_time_seconds, 4),
            status="PASS" if schema_result.is_valid else "FAIL",
        )

        outcome = ValidationOutcome(
            dataset_name=dataset_name,
            source_path=source_path,
            file_format=file_format,
            records=list(records),
            validated_records=validated_records,
            invalid_records=invalid_records,
            schema_result=schema_result,
            report=quality_report,
            errors=schema_result.errors.copy(),
            warnings=schema_result.warnings.copy(),
        )

        logger.info(
            "Validation result | dataset=%s | status=%s | rows_valid=%s | rows_invalid=%s | time=%.4fs",
            dataset_name,
            quality_report.status,
            quality_report.rows_valid,
            quality_report.rows_invalid,
            processing_time_seconds,
        )
        if outcome.errors:
            logger.warning(
                "Validation errors for %s: %s", dataset_name, "; ".join(outcome.errors)
            )
        if outcome.warnings:
            logger.warning(
                "Validation warnings for %s: %s",
                dataset_name,
                "; ".join(outcome.warnings),
            )

        return outcome
