"""ETL foundation package for GridSense AI Phase 4.1.

This package provides raw-file extraction, schema validation, data quality
reporting, and a reusable pipeline for validated staging datasets.
"""

from src.etl.extract import RawDataset, discover_raw_files, load_raw_dataset
from src.etl.exceptions import (
    ETLException,
    ETLFileNotFoundError,
    ETLParseError,
    ETLStageError,
    ETLValidationError,
)
from src.etl.pipeline import ETLPipeline, ETLRunResult
from src.etl.quality import DataQualityReport
from src.etl.schema_validator import (
    ColumnRule,
    SchemaDefinition,
    SchemaValidationResult,
    SchemaValidator,
)
from src.etl.validate import ValidationOutcome, ValidationService

__all__ = [
    "RawDataset",
    "discover_raw_files",
    "load_raw_dataset",
    "ETLException",
    "ETLFileNotFoundError",
    "ETLParseError",
    "ETLStageError",
    "ETLValidationError",
    "ETLPipeline",
    "ETLRunResult",
    "DataQualityReport",
    "ColumnRule",
    "SchemaDefinition",
    "SchemaValidationResult",
    "SchemaValidator",
    "ValidationOutcome",
    "ValidationService",
]
