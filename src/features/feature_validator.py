"""Feature validation for Phase 4.3 – post-computation quality gate.

:func:`validate_features` inspects a list of feature-enriched record dicts and
reports:

- Missing values in feature columns (``None`` / ``""``)
- Infinite values (``math.isinf``)
- NaN values (``math.isnan``)
- Values outside the configured valid range (``valid_min`` / ``valid_max``)
- Duplicate feature column names within a single record
- Invalid type coercions (non-numeric values in numeric features)

The validator is **non-destructive** — it never modifies records.  All issues
are collected as warning strings and returned alongside summary counts.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from src.features.feature_metadata import FeatureMetadata


def _safe_float(value: Any) -> Optional[float]:
    """Try to coerce *value* to float; return ``None`` on failure."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_features(
    records: List[Dict[str, Any]],
    feature_columns: List[str],
    metadata_map: Dict[str, FeatureMetadata],
) -> Tuple[Dict[str, int], List[str]]:
    """Validate feature columns across all records.

    Parameters
    ----------
    records:
        Feature-enriched dataset rows.
    feature_columns:
        List of feature column names to validate.
    metadata_map:
        Mapping of feature name → :class:`FeatureMetadata` for range bounds.

    Returns
    -------
    tuple[dict[str, int], list[str]]
        ``(summary_counts, warning_messages)``

        Summary keys:

        - ``"missing"``   — cells that are ``None`` or ``""``
        - ``"infinite"``  — cells containing ``math.inf`` or ``-math.inf``
        - ``"nan"``       — cells containing ``math.nan``
        - ``"out_of_range"`` — cells outside ``[valid_min, valid_max]``
        - ``"type_errors"``  — non-numeric values in numeric feature columns
        - ``"total_checked"`` — total (row × column) cells inspected
    """
    summary: Dict[str, int] = {
        "missing": 0,
        "infinite": 0,
        "nan": 0,
        "out_of_range": 0,
        "type_errors": 0,
        "total_checked": 0,
    }
    warnings: List[str] = []

    # Check for duplicate column names in feature list
    seen: set[str] = set()
    for col in feature_columns:
        if col in seen:
            warnings.append(f"Duplicate feature column name detected: '{col}'.")
        seen.add(col)

    for row_index, record in enumerate(records):
        for col in feature_columns:
            summary["total_checked"] += 1
            value = record.get(col)
            meta = metadata_map.get(col)

            # ---- Missing ----
            if value is None or value == "":
                summary["missing"] += 1
                warnings.append(
                    f"Missing value | row={row_index} | feature='{col}'."
                )
                continue

            # ---- Type check for numeric features ----
            f_value = _safe_float(value)
            if meta is not None and meta.output_type in ("float", "int"):
                if f_value is None:
                    summary["type_errors"] += 1
                    warnings.append(
                        f"Type error | row={row_index} | feature='{col}'"
                        f" | value={value!r} (expected numeric)."
                    )
                    continue

            if f_value is None:
                continue  # non-numeric feature type, skip numeric checks

            # ---- Infinite ----
            if math.isinf(f_value):
                summary["infinite"] += 1
                warnings.append(
                    f"Infinite value | row={row_index} | feature='{col}'"
                    f" | value={f_value}."
                )
                continue

            # ---- NaN ----
            if math.isnan(f_value):
                summary["nan"] += 1
                warnings.append(
                    f"NaN value | row={row_index} | feature='{col}'."
                )
                continue

            # ---- Range check ----
            if meta is not None:
                if meta.valid_min is not None and f_value < meta.valid_min:
                    summary["out_of_range"] += 1
                    warnings.append(
                        f"Out-of-range | row={row_index} | feature='{col}'"
                        f" | value={f_value} < min={meta.valid_min}."
                    )
                elif meta.valid_max is not None and f_value > meta.valid_max:
                    summary["out_of_range"] += 1
                    warnings.append(
                        f"Out-of-range | row={row_index} | feature='{col}'"
                        f" | value={f_value} > max={meta.valid_max}."
                    )

    return summary, warnings
