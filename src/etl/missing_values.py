"""Missing value handling strategies for Phase 4.2.

Provides a single public function :func:`handle_missing_values` that applies
configurable per-column strategies to a list of record dictionaries.

All eight strategies are fully auditable: every cell modification or row
deletion emits an :class:`~src.etl.audit.AuditRecord`.

Supported strategies
--------------------
- ``drop``          – Drop any row that contains a missing value in this column.
- ``mean``          – Fill with the column arithmetic mean (numeric only).
- ``median``        – Fill with the column median (numeric only).
- ``mode``          – Fill with the most-frequent observed value.
- ``forward_fill``  – Propagate the last seen non-missing value forward.
- ``backward_fill`` – Propagate the next seen non-missing value backward.
- ``interpolate``   – Linear interpolation between adjacent non-missing values.
- ``constant``      – Fill with a fixed value supplied via configuration.

Missing sentinels
-----------------
The following values are treated as missing: ``None``, ``""``, ``"nan"``,
``"NaN"``, ``"null"``, ``"NULL"``.
"""

from __future__ import annotations

from statistics import mean, median, mode
from typing import Any, Dict, List, Tuple

from src.etl.audit import AuditRecord
from src.etl.cleaning_rules import MissingValueRule


def _is_missing(value: Any) -> bool:
    """Return ``True`` if *value* should be treated as missing."""
    return value in (None, "", "nan", "NaN", "null", "NULL")


def _numeric_values(records: List[Dict[str, Any]], column: str) -> List[float]:
    """Collect all non-missing, parseable float values for *column*.

    Parameters
    ----------
    records:
        Dataset rows.
    column:
        Column name to inspect.

    Returns
    -------
    list[float]
        Only rows that contain parseable numeric values are included.
    """
    values: List[float] = []
    for record in records:
        value = record.get(column)
        if _is_missing(value):
            continue
        try:
            values.append(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return values


def handle_missing_values(
    records: List[Dict[str, Any]],
    dataset_name: str,
    rules: Dict[str, MissingValueRule],
) -> Tuple[List[Dict[str, Any]], int, List[AuditRecord], List[str]]:
    """Apply configurable missing-value strategies to every specified column.

    Strategies are applied in the order they appear in *rules*.  For the
    ``drop`` strategy the row count may decrease; all other strategies mutate
    cells in-place and preserve row count.

    Parameters
    ----------
    records:
        Mutable list of record dictionaries representing the staging dataset.
    dataset_name:
        Dataset identifier used in audit records.
    rules:
        Per-column :class:`~src.etl.cleaning_rules.MissingValueRule` map.

    Returns
    -------
    tuple[list[dict], int, list[AuditRecord], list[str]]
        ``(cleaned_records, fixed_count, audit_records, warnings)``

        - *cleaned_records*: Records after missing-value handling.
        - *fixed_count*:     Number of cells filled **or** rows dropped.
        - *audit_records*:   Audit trail for every modification.
        - *warnings*:        Non-fatal issues (e.g. unsupported strategy).
    """
    fixed_count = 0
    audit: List[AuditRecord] = []
    warnings: List[str] = []

    if not records:
        return records, fixed_count, audit, warnings

    retained_records = records

    for column, rule in rules.items():
        strategy = rule.strategy

        # ------------------------------------------------------------------
        # DROP – remove rows that are missing in this column
        # ------------------------------------------------------------------
        if strategy == "drop":
            filtered: List[Dict[str, Any]] = []
            for row_index, record in enumerate(retained_records):
                value = record.get(column)
                if _is_missing(value):
                    fixed_count += 1
                    audit.append(
                        AuditRecord(
                            dataset=dataset_name,
                            column=column,
                            original_value=value,
                            new_value="<ROW_DROPPED>",
                            cleaning_rule="missing_drop",
                            row_index=row_index,
                        )
                    )
                    continue
                filtered.append(record)
            retained_records = filtered
            continue

        # ------------------------------------------------------------------
        # FORWARD FILL
        # ------------------------------------------------------------------
        if strategy == "forward_fill":
            previous: Any = None
            for row_index, record in enumerate(retained_records):
                value = record.get(column)
                if _is_missing(value) and previous is not None:
                    record[column] = previous
                    fixed_count += 1
                    audit.append(
                        AuditRecord(
                            dataset=dataset_name,
                            column=column,
                            original_value=value,
                            new_value=previous,
                            cleaning_rule="missing_forward_fill",
                            row_index=row_index,
                        )
                    )
                elif not _is_missing(value):
                    previous = value
            continue

        # ------------------------------------------------------------------
        # BACKWARD FILL
        # ------------------------------------------------------------------
        if strategy == "backward_fill":
            next_value: Any = None
            for row_index in range(len(retained_records) - 1, -1, -1):
                record = retained_records[row_index]
                value = record.get(column)
                if _is_missing(value) and next_value is not None:
                    record[column] = next_value
                    fixed_count += 1
                    audit.append(
                        AuditRecord(
                            dataset=dataset_name,
                            column=column,
                            original_value=value,
                            new_value=next_value,
                            cleaning_rule="missing_backward_fill",
                            row_index=row_index,
                        )
                    )
                elif not _is_missing(value):
                    next_value = value
            continue

        # ------------------------------------------------------------------
        # LINEAR INTERPOLATION
        # ------------------------------------------------------------------
        if strategy == "interpolate":
            for row_index, record in enumerate(retained_records):
                value = record.get(column)
                if not _is_missing(value):
                    continue

                previous_num: float | None = None
                next_num: float | None = None

                for back_index in range(row_index - 1, -1, -1):
                    back_val = retained_records[back_index].get(column)
                    if _is_missing(back_val):
                        continue
                    try:
                        previous_num = float(back_val)  # type: ignore[arg-type]
                        break
                    except (TypeError, ValueError):
                        break

                for next_index in range(row_index + 1, len(retained_records)):
                    next_val = retained_records[next_index].get(column)
                    if _is_missing(next_val):
                        continue
                    try:
                        next_num = float(next_val)  # type: ignore[arg-type]
                        break
                    except (TypeError, ValueError):
                        break

                if previous_num is not None and next_num is not None:
                    interpolated = (previous_num + next_num) / 2.0
                    record[column] = interpolated
                    fixed_count += 1
                    audit.append(
                        AuditRecord(
                            dataset=dataset_name,
                            column=column,
                            original_value=value,
                            new_value=interpolated,
                            cleaning_rule="missing_interpolate",
                            row_index=row_index,
                        )
                    )
            continue

        # ------------------------------------------------------------------
        # Aggregate-fill strategies (mean / median / mode / constant)
        # ------------------------------------------------------------------
        fill_value: Any = None
        numeric_values = _numeric_values(retained_records, column)

        if strategy == "mean":
            fill_value = mean(numeric_values) if numeric_values else None
        elif strategy == "median":
            fill_value = median(numeric_values) if numeric_values else None
        elif strategy == "mode":
            observed = [
                record.get(column)
                for record in retained_records
                if not _is_missing(record.get(column))
            ]
            if observed:
                try:
                    fill_value = mode(observed)
                except Exception:
                    fill_value = observed[0]
        elif strategy == "constant":
            fill_value = rule.constant_value
        else:
            warnings.append(
                f"Unsupported missing strategy '{strategy}' for column '{column}'."
            )
            continue

        if fill_value is None and strategy != "constant":
            warnings.append(
                f"Missing strategy '{strategy}' for column '{column}'"
                " could not compute a fill value."
            )
            continue

        for row_index, record in enumerate(retained_records):
            value = record.get(column)
            if _is_missing(value):
                record[column] = fill_value
                fixed_count += 1
                audit.append(
                    AuditRecord(
                        dataset=dataset_name,
                        column=column,
                        original_value=value,
                        new_value=fill_value,
                        cleaning_rule=f"missing_{strategy}",
                        row_index=row_index,
                    )
                )

    return retained_records, fixed_count, audit, warnings
