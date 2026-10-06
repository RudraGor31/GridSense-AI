"""Feature validation utilities for Phase 4.3.

Validates engineered feature datasets for common data-quality issues before
they are persisted.  The validator is deliberately non-destructive — it only
reports issues as warnings or errors; it never modifies the records.

Checks performed
----------------
- Missing values (``None`` or empty string) in feature columns.
- Infinite values (``float("inf")``, ``float("-inf")``).
- NaN values (``float("nan")``).
- Unexpected value ranges (configurable per feature).
- Duplicate feature columns.
- Invalid calculations (non-numeric values in numeric feature columns).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class FeatureValidationResult:
    """Result of a feature validation pass.

    Attributes
    ----------
    dataset:
        Name of the dataset that was validated.
    feature_columns:
        Feature column names that were inspected.
    total_rows:
        Number of rows validated.
    missing_count:
        Cells with ``None`` or empty-string values.
    infinite_count:
        Cells with ``±inf`` values.
    nan_count:
        Cells with ``NaN`` values.
    out_of_range_count:
        Cells that violate configured numeric bounds.
    duplicate_columns:
        Feature column names that appear more than once across the record keys.
    invalid_calc_count:
        Non-numeric cells in columns declared as numeric features.
    warnings:
        Non-fatal issue messages.
    errors:
        Fatal issue messages (e.g. duplicate columns).
    is_valid:
        ``True`` if there are no errors (warnings are permitted).
    """

    dataset: str
    feature_columns: List[str]
    total_rows: int = 0
    missing_count: int = 0
    infinite_count: int = 0
    nan_count: int = 0
    out_of_range_count: int = 0
    duplicate_columns: List[str] = field(default_factory=list)
    invalid_calc_count: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    is_valid: bool = True

    def _recompute_validity(self) -> None:
        self.is_valid = len(self.errors) == 0


class FeatureValidator:
    """Validate engineered feature records for data-quality issues.

    Parameters
    ----------
    numeric_columns:
        Feature column names that are expected to hold numeric values.
        Non-numeric values in these columns are counted as invalid calculations.
    range_bounds:
        Optional per-column numeric bounds ``{column: (min, max)}``.  Values
        outside these bounds are reported as out-of-range warnings.
    allow_missing:
        If ``True``, missing values produce warnings rather than errors.
    """

    def __init__(
        self,
        numeric_columns: Optional[List[str]] = None,
        range_bounds: Optional[Dict[str, Tuple[float, float]]] = None,
        allow_missing: bool = True,
    ) -> None:
        self._numeric_columns = set(numeric_columns or [])
        self._range_bounds = range_bounds or {}
        self._allow_missing = allow_missing

    def validate(
        self,
        records: List[Dict[str, Any]],
        dataset: str,
        feature_columns: List[str],
    ) -> FeatureValidationResult:
        """Run all validation checks on *records*.

        Parameters
        ----------
        records:
            Engineered feature records to validate.
        dataset:
            Dataset name for the result report.
        feature_columns:
            Feature column names to inspect.

        Returns
        -------
        FeatureValidationResult
        """
        result = FeatureValidationResult(
            dataset=dataset,
            feature_columns=list(feature_columns),
            total_rows=len(records),
        )

        # ---- Duplicate column check (across keys of first record) ----
        if records:
            all_keys = list(records[0].keys())
            seen: set[str] = set()
            dupes: List[str] = []
            for k in all_keys:
                if k in feature_columns:
                    if k in seen:
                        dupes.append(k)
                    seen.add(k)
            if dupes:
                result.duplicate_columns = dupes
                result.errors.append(f"Duplicate feature columns detected: {dupes}")

        # ---- Per-row checks ----
        for row_idx, record in enumerate(records):
            for col in feature_columns:
                value = record.get(col)

                # Missing
                if value is None or value == "":
                    result.missing_count += 1
                    msg = f"Missing value | row={row_idx} | column={col}"
                    if self._allow_missing:
                        result.warnings.append(msg)
                    else:
                        result.errors.append(msg)
                    continue

                # Numeric checks
                if col in self._numeric_columns:
                    try:
                        fval = float(value)  # type: ignore[arg-type]
                    except (TypeError, ValueError):
                        result.invalid_calc_count += 1
                        result.warnings.append(
                            f"Non-numeric value | row={row_idx} | column={col} | value={value!r}"
                        )
                        continue

                    if math.isinf(fval):
                        result.infinite_count += 1
                        result.warnings.append(
                            f"Infinite value | row={row_idx} | column={col}"
                        )
                    elif math.isnan(fval):
                        result.nan_count += 1
                        result.warnings.append(
                            f"NaN value | row={row_idx} | column={col}"
                        )
                    elif col in self._range_bounds:
                        lo, hi = self._range_bounds[col]
                        if fval < lo or fval > hi:
                            result.out_of_range_count += 1
                            result.warnings.append(
                                f"Out-of-range | row={row_idx} | column={col}"
                                f" | value={fval} | expected=[{lo}, {hi}]"
                            )

        result._recompute_validity()
        return result
