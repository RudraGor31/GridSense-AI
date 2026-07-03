"""Schema validation helpers for GridSense AI ETL."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(slots=True)
class ColumnRule:
    """Declarative rule for a single column."""

    name: str
    data_type: str
    required: bool = True
    allow_null: bool = False
    allow_negative: bool = True
    minimum: Optional[float] = None
    maximum: Optional[float] = None


@dataclass(slots=True)
class SchemaDefinition:
    """Schema contract for a tabular dataset."""

    name: str
    columns: Dict[str, ColumnRule]
    allow_extra_columns: bool = True
    unique_key: Optional[Tuple[str, ...]] = None


@dataclass(slots=True)
class SchemaValidationResult:
    """Validation outcome for a dataset."""

    dataset_name: str
    rows_checked: int
    valid_rows: int
    invalid_rows: int
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_columns: List[str] = field(default_factory=list)
    unexpected_columns: List[str] = field(default_factory=list)
    duplicate_records: List[int] = field(default_factory=list)
    invalid_row_indices: List[int] = field(default_factory=list)


class SchemaValidator:
    """Validate tabular records against declarative schema definitions."""

    def validate(
        self, records: Sequence[Dict[str, Any]], schema: SchemaDefinition
    ) -> SchemaValidationResult:
        """Validate records and return a structured result."""

        errors: List[str] = []
        warnings: List[str] = []
        invalid_row_indices: List[int] = []
        duplicate_records: List[int] = []

        rows_checked = len(records)
        if rows_checked == 0:
            errors.append("Dataset is empty.")
            return SchemaValidationResult(
                dataset_name=schema.name,
                rows_checked=0,
                valid_rows=0,
                invalid_rows=0,
                is_valid=False,
                errors=errors,
                warnings=warnings,
            )

        required_columns = [
            name for name, rule in schema.columns.items() if rule.required
        ]
        observed_columns: set[str] = set()
        for record in records:
            observed_columns.update(record.keys())

        missing_columns = sorted(
            column for column in required_columns if column not in observed_columns
        )
        if missing_columns:
            errors.extend(
                f"Missing required column: {column}" for column in missing_columns
            )

        unexpected_columns = sorted(
            column for column in observed_columns if column not in schema.columns
        )
        if unexpected_columns:
            message = f"Unexpected columns observed: {', '.join(unexpected_columns)}"
            if schema.allow_extra_columns:
                warnings.append(message)
            else:
                errors.append(message)

        seen_keys = set()
        valid_rows = 0

        for index, record in enumerate(records):
            row_errors: List[str] = []

            if schema.unique_key:
                key = tuple(record.get(column) for column in schema.unique_key)
                if key in seen_keys:
                    duplicate_records.append(index)
                    warnings.append(f"Duplicate record detected at row {index}.")
                else:
                    seen_keys.add(key)

            for column_name, rule in schema.columns.items():
                value = record.get(column_name)
                if value in (None, ""):
                    if rule.required and not rule.allow_null:
                        row_errors.append(
                            f"Row {index}: missing required value for '{column_name}'."
                        )
                    continue

                if not self._matches_type(value, rule.data_type):
                    row_errors.append(
                        f"Row {index}: column '{column_name}' has invalid type; expected {rule.data_type}."
                    )
                    continue

                numeric_value = self._to_number(value)
                if numeric_value is not None:
                    if not rule.allow_negative and numeric_value < 0:
                        row_errors.append(
                            f"Row {index}: column '{column_name}' cannot contain negative values."
                        )
                    if rule.minimum is not None and numeric_value < rule.minimum:
                        row_errors.append(
                            f"Row {index}: column '{column_name}' is below minimum {rule.minimum}."
                        )
                    if rule.maximum is not None and numeric_value > rule.maximum:
                        row_errors.append(
                            f"Row {index}: column '{column_name}' is above maximum {rule.maximum}."
                        )

                if rule.data_type == "timestamp" and not self._is_timestamp(value):
                    row_errors.append(
                        f"Row {index}: column '{column_name}' is not a valid timestamp."
                    )

            if row_errors:
                invalid_row_indices.append(index)
                errors.extend(row_errors)
            else:
                valid_rows += 1

        invalid_rows = rows_checked - valid_rows
        return SchemaValidationResult(
            dataset_name=schema.name,
            rows_checked=rows_checked,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            is_valid=invalid_rows == 0 and not errors,
            errors=errors,
            warnings=warnings,
            missing_columns=missing_columns,
            unexpected_columns=unexpected_columns,
            duplicate_records=duplicate_records,
            invalid_row_indices=invalid_row_indices,
        )

    @staticmethod
    def _matches_type(value: Any, data_type: str) -> bool:
        if data_type == "string":
            return isinstance(value, str)
        if data_type == "integer":
            if isinstance(value, bool):
                return False
            try:
                return float(value).is_integer()
            except (TypeError, ValueError):
                return False
        if data_type == "number":
            try:
                float(value)
                return True
            except (TypeError, ValueError):
                return False
        if data_type == "boolean":
            return isinstance(value, bool) or str(value).strip().lower() in {
                "true",
                "false",
                "1",
                "0",
                "yes",
                "no",
            }
        if data_type == "timestamp":
            return SchemaValidator._is_timestamp(value)
        return True

    @staticmethod
    def _to_number(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_timestamp(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        candidate = value.replace("Z", "+00:00")
        try:
            datetime.fromisoformat(candidate)
            return True
        except ValueError:
            return False
