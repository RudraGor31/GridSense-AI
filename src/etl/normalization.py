"""Unit conversion, coordinate validation, and outlier flagging for Phase 4.2.

This module provides three independent, pure-function utilities:

:func:`standardize_units`
    Converts numeric column values from a source unit to a canonical target unit
    using a static lookup table.  Every conversion is audited.

:func:`validate_coordinates`
    Validates that ``latitude`` values fall within [−90, 90] and
    ``longitude`` values fall within [−180, 180].  Invalid coordinates are
    reported as warnings; rows are **never** removed.

:func:`flag_outliers`
    Flags statistical outliers using IQR or Z-score methods.  Outliers are
    **never removed automatically** – they are only reported as warnings so that
    domain experts can review and decide.

Supported unit conversions
--------------------------
===================  ===========  ====================
Source               Target       Notes
===================  ===========  ====================
celsius              celsius      identity
fahrenheit           celsius      (x − 32) × 5/9
kelvin               celsius      x − 273.15
m/s                  km/h         × 3.6
km/h                 km/h         identity
cm                   mm           × 10
mm                   mm           identity
W                    kW           ÷ 1000
kW                   kW           identity
kW                   MW           ÷ 1000
MW                   MW           identity
Pa                   hPa          ÷ 100
hPa                  hPa          identity
ratio                percent      × 100
percent              percent      identity
===================  ===========  ====================
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any, Callable, Dict, List, Mapping, Tuple

from src.etl.audit import AuditRecord
from src.etl.cleaning_rules import UnitRule

# ---------------------------------------------------------------------------
# Unit conversion table
# ---------------------------------------------------------------------------

#: Static mapping of ``(source_unit, target_unit)`` → conversion callable.
#: All unit strings are stored lower-case.
UNIT_CONVERSIONS: Dict[Tuple[str, str], Callable[[float], float]] = {
    ("celsius", "celsius"): lambda x: x,
    ("fahrenheit", "celsius"): lambda x: (x - 32.0) * 5.0 / 9.0,
    ("kelvin", "celsius"): lambda x: x - 273.15,
    ("m/s", "km/h"): lambda x: x * 3.6,
    ("km/h", "km/h"): lambda x: x,
    ("cm", "mm"): lambda x: x * 10.0,
    ("mm", "mm"): lambda x: x,
    ("w", "kw"): lambda x: x / 1000.0,
    ("kw", "kw"): lambda x: x,
    ("kw", "mw"): lambda x: x / 1000.0,
    ("mw", "mw"): lambda x: x,
    ("pa", "hpa"): lambda x: x / 100.0,
    ("hpa", "hpa"): lambda x: x,
    ("ratio", "percent"): lambda x: x * 100.0,
    ("percent", "percent"): lambda x: x,
}


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def standardize_units(
    records: List[Dict[str, Any]],
    dataset_name: str,
    unit_rules: Mapping[str, UnitRule],
) -> Tuple[List[Dict[str, Any]], List[AuditRecord], List[str]]:
    """Convert column values from source units to canonical target units.

    Only cells whose converted value differs from the original value produce an
    audit record (identity conversions such as ``mw → mw`` are silent).

    Parameters
    ----------
    records:
        Mutable list of record dictionaries.
    dataset_name:
        Dataset identifier used in audit records.
    unit_rules:
        Per-column :class:`~src.etl.cleaning_rules.UnitRule` map.

    Returns
    -------
    tuple[list[dict], list[AuditRecord], list[str]]
        ``(records, audit_records, warnings)``
    """
    audit: List[AuditRecord] = []
    warnings: List[str] = []

    for row_index, record in enumerate(records):
        for column, rule in unit_rules.items():
            if column not in record or record[column] in (None, ""):
                continue

            conversion = UNIT_CONVERSIONS.get(
                (rule.source_unit.lower(), rule.target_unit.lower())
            )
            if conversion is None:
                warnings.append(
                    f"No unit conversion from '{rule.source_unit}' to"
                    f" '{rule.target_unit}' for column '{column}'."
                )
                continue

            try:
                current = float(record[column])  # type: ignore[arg-type]
                converted = conversion(current)
            except (TypeError, ValueError):
                warnings.append(
                    f"Unit conversion failed for column '{column}' at row {row_index}."
                )
                continue

            if converted != current:
                record[column] = converted
                audit.append(
                    AuditRecord(
                        dataset=dataset_name,
                        column=column,
                        original_value=current,
                        new_value=converted,
                        cleaning_rule=(
                            f"unit_{rule.source_unit}_to_{rule.target_unit}"
                        ),
                        row_index=row_index,
                    )
                )

    return records, audit, warnings


def validate_coordinates(records: List[Dict[str, Any]]) -> List[str]:
    """Validate ``latitude`` and ``longitude`` ranges in every row.

    - Latitude must be in [−90, 90].
    - Longitude must be in [−180, 180].

    Invalid coordinates are reported as warnings; rows are never dropped.

    Parameters
    ----------
    records:
        Dataset rows (must contain ``"latitude"`` and ``"longitude"`` keys to
        be checked; rows without these keys are silently skipped).

    Returns
    -------
    list[str]
        One warning message per invalid coordinate encountered.
    """
    warnings: List[str] = []
    for row_index, record in enumerate(records):
        lat = record.get("latitude")
        lon = record.get("longitude")
        if lat in (None, "") or lon in (None, ""):
            continue

        try:
            lat_value = float(lat)  # type: ignore[arg-type]
            lon_value = float(lon)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            warnings.append(f"Invalid coordinate format at row {row_index}.")
            continue

        if lat_value < -90.0 or lat_value > 90.0:
            warnings.append(
                f"Invalid latitude at row {row_index}: {lat_value}"
                " (expected -90 to 90)."
            )
        if lon_value < -180.0 or lon_value > 180.0:
            warnings.append(
                f"Invalid longitude at row {row_index}: {lon_value}"
                " (expected -180 to 180)."
            )

    return warnings


def flag_outliers(
    records: List[Dict[str, Any]],
    outlier_columns: Mapping[str, str],
) -> Tuple[int, List[str]]:
    """Flag statistical outliers using IQR or Z-score — never remove them.

    IQR method
    ~~~~~~~~~~
    A value is flagged if it falls below ``Q1 − 1.5 × IQR`` or above
    ``Q3 + 1.5 × IQR``.  Q1 and Q3 are computed using the nearest-rank method
    from the sorted list of non-missing values.

    Z-score method
    ~~~~~~~~~~~~~~
    A value is flagged if ``|z| > 3.0``, where
    ``z = (value − μ) / σ`` (population standard deviation).

    Parameters
    ----------
    records:
        Dataset rows.
    outlier_columns:
        Mapping of ``{column_name: method}`` where *method* is
        ``"iqr"`` or ``"zscore"``.

    Returns
    -------
    tuple[int, list[str]]
        ``(total_flagged, warning_messages)``

        - *total_flagged*:    Cumulative count of outlier cells across all columns.
        - *warning_messages*: One message per outlier, including row index,
          column name, value, and (for Z-score) the z-value.
    """
    flagged = 0
    warnings: List[str] = []

    for column, method in outlier_columns.items():
        numeric_values: List[float] = []
        indexed_values: List[Tuple[int, float]] = []

        for index, record in enumerate(records):
            value = record.get(column)
            if value in (None, ""):
                continue
            try:
                numeric_value = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            numeric_values.append(numeric_value)
            indexed_values.append((index, numeric_value))

        if len(numeric_values) < 3:
            # Not enough data for meaningful outlier detection
            continue

        if method == "iqr":
            sorted_values = sorted(numeric_values)
            n = len(sorted_values)
            q1_idx = int(0.25 * (n - 1))
            q3_idx = int(0.75 * (n - 1))
            q1 = sorted_values[q1_idx]
            q3 = sorted_values[q3_idx]
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr

            for row_index, value in indexed_values:
                if value < lower or value > upper:
                    flagged += 1
                    warnings.append(
                        f"Outlier flagged by IQR | row={row_index} | column={column}"
                        f" | value={value} | bounds=[{round(lower, 4)}, {round(upper, 4)}]."
                    )

        elif method == "zscore":
            avg = mean(numeric_values)
            std = pstdev(numeric_values)
            if std == 0:
                continue
            for row_index, value in indexed_values:
                z = abs((value - avg) / std)
                if z > 3.0:
                    flagged += 1
                    warnings.append(
                        f"Outlier flagged by Z-score | row={row_index}"
                        f" | column={column} | value={value} | z={round(z, 2)}."
                    )
        else:
            warnings.append(
                f"Unsupported outlier method '{method}' for column '{column}'."
            )

    return flagged, warnings
