"""Column, text, type, and categorical standardization utilities for Phase 4.2.

This module provides two primary public functions:

:func:`standardize_columns`
    Normalises every column name in a dataset to ``snake_case``, strips
    invisible Unicode characters from string values, and removes duplicate
    columns produced by normalisation collisions.

:func:`standardize_types_and_categories`
    Casts cell values to their configured target data types and maps raw
    categorical strings to their canonical forms.

Text cleaning
-------------
All string values pass through :func:`normalize_text` which:

1. Applies NFKC Unicode normalisation (e.g. converts full-width characters).
2. Removes invisible characters (zero-width space ``U+200B``, BOM ``U+FEFF``).
3. Collapses runs of whitespace to a single space.
4. Strips leading and trailing whitespace.

Timestamp normalisation
-----------------------
:func:`to_timestamp_utc` converts any parseable ISO-8601 timestamp string to a
UTC ``Z``-suffixed string.  Naive datetimes are assumed to be UTC.  Timezone
metadata (``"UTC"``, ``"INVALID"``, ``"UNKNOWN"``) is returned alongside the
converted value so it can be stored in the clean dataset envelope.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Tuple

from src.etl.audit import AuditRecord

# ---------------------------------------------------------------------------
# Text and column-name normalisation helpers
# ---------------------------------------------------------------------------


def normalize_column_name(name: str) -> str:
    """Normalise a column name to ``snake_case`` with only legal characters.

    Steps applied
    ~~~~~~~~~~~~~
    1. NFKC Unicode normalisation.
    2. Strip leading/trailing whitespace and convert to lower-case.
    3. Remove characters outside ``[a-z0-9_ ]``.
    4. Collapse whitespace runs to a single underscore.
    5. Collapse repeated underscores.
    6. Strip leading/trailing underscores.

    Parameters
    ----------
    name:
        Raw column name as it appears in the source data.

    Returns
    -------
    str
        Normalised snake_case column name, e.g. ``" Demand MW "`` → ``"demand_mw"``.
    """
    normalized = unicodedata.normalize("NFKC", name or "")
    normalized = normalized.strip().lower()
    normalized = re.sub(r"[^a-z0-9_\s]", "", normalized)
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def normalize_text(value: Any) -> Any:
    """Clean a string value: normalise Unicode, remove invisible chars, trim.

    Non-string values are returned unchanged.

    Parameters
    ----------
    value:
        The cell value to normalise.

    Returns
    -------
    Any
        Cleaned string, or the original value if it is not a ``str``.
    """
    if not isinstance(value, str):
        return value

    cleaned = unicodedata.normalize("NFKC", value)
    # Remove zero-width space and BOM
    cleaned = cleaned.replace("\u200b", "").replace("\ufeff", "")
    # Collapse repeated whitespace (including tabs and newlines)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Public transformation functions
# ---------------------------------------------------------------------------


def standardize_columns(
    records: List[Dict[str, Any]],
    dataset_name: str,
) -> Tuple[List[Dict[str, Any]], int, List[AuditRecord]]:
    """Normalise column names and clean string values in every row.

    For each row:

    - Every column name is passed through :func:`normalize_column_name`.
    - If the normalised name differs from the original, a rename audit record
      is emitted and *rename_count* is incremented.
    - If two original columns normalise to the *same* name the second one is
      dropped (a collision audit record is emitted).
    - Every string cell value is passed through :func:`normalize_text`.

    Parameters
    ----------
    records:
        Input dataset rows.
    dataset_name:
        Dataset identifier for audit records.

    Returns
    -------
    tuple[list[dict], int, list[AuditRecord]]
        ``(standardized_records, rename_count, audit_records)``
    """
    rename_count = 0
    audit_records: List[AuditRecord] = []
    standardized: List[Dict[str, Any]] = []

    for row_index, record in enumerate(records):
        new_record: Dict[str, Any] = {}
        for column, value in record.items():
            normalized_column = normalize_column_name(column)

            if normalized_column != column:
                rename_count += 1
                audit_records.append(
                    AuditRecord(
                        dataset=dataset_name,
                        column=column,
                        original_value=column,
                        new_value=normalized_column,
                        cleaning_rule="column_snake_case",
                        row_index=row_index,
                    )
                )

            if normalized_column in new_record:
                # Collision: second column with same normalised name is dropped
                audit_records.append(
                    AuditRecord(
                        dataset=dataset_name,
                        column=normalized_column,
                        original_value=value,
                        new_value=new_record[normalized_column],
                        cleaning_rule="duplicate_column_dropped",
                        row_index=row_index,
                    )
                )
                continue

            new_record[normalized_column] = normalize_text(value)

        standardized.append(new_record)

    return standardized, rename_count, audit_records


def to_bool(value: Any) -> Any:
    """Normalise common boolean-like values to Python ``bool``.

    Recognised truthy strings: ``"1"``, ``"true"``, ``"yes"``, ``"y"``.
    Recognised falsy strings:  ``"0"``, ``"false"``, ``"no"``, ``"n"``.

    Parameters
    ----------
    value:
        Raw cell value.

    Returns
    -------
    bool | None | Any
        ``True``, ``False``, ``None`` for ``None`` input, or the original
        *value* if it cannot be mapped.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return None

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return value


def to_timestamp_utc(value: Any) -> Tuple[Any, str]:
    """Convert an ISO-8601 timestamp to a UTC ``Z``-suffixed string.

    Naive datetimes (no timezone info) are assumed to be UTC.

    Parameters
    ----------
    value:
        Raw timestamp value.  Supported inputs: ``str`` (ISO-8601),
        ``datetime`` object, or ``None``/``""``.

    Returns
    -------
    tuple[Any, str]
        ``(utc_iso_string, tz_label)`` where *tz_label* is one of:

        - ``"UTC"``     – successful conversion.
        - ``"INVALID"`` – string could not be parsed as a datetime.
        - ``"UNKNOWN"`` – non-string, non-datetime value was received.
    """
    if value in (None, ""):
        return None, "UTC"

    if isinstance(value, datetime):
        dt = value
    else:
        if not isinstance(value, str):
            return value, "UNKNOWN"
        candidate = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError:
            return value, "INVALID"

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.isoformat().replace("+00:00", "Z"), "UTC"


def standardize_types_and_categories(
    records: List[Dict[str, Any]],
    dataset_name: str,
    dtypes: Mapping[str, str],
    categoricals: Mapping[str, Mapping[str, str]],
    timestamp_columns: Mapping[str, Dict[str, str]],
) -> Tuple[List[Dict[str, Any]], int, List[AuditRecord], Dict[str, str], List[str]]:
    """Apply data-type coercion and categorical value normalisation.

    Type coercion rules
    ~~~~~~~~~~~~~~~~~~~
    ==================  ===================================================
    Target type         Conversion applied
    ==================  ===================================================
    ``"integer"``       ``int(float(value))`` for non-null values.
    ``"float"``         ``float(value)`` for non-null values.
    ``"boolean"``       :func:`to_bool`.
    ``"string"``        ``str(value)`` + :func:`normalize_text`.
    ``"date"``          :func:`to_timestamp_utc` (returns ISO date string).
    ``"timestamp"``     :func:`to_timestamp_utc` (returns ISO datetime ``Z``).
    ==================  ===================================================

    Parameters
    ----------
    records:
        Mutable list of record dictionaries.
    dataset_name:
        Dataset identifier for audit records.
    dtypes:
        Per-column target type strings.
    categoricals:
        Per-column value mapping dictionaries
        ``{lower_raw_value: canonical_value}``.
    timestamp_columns:
        Per-column timestamp configuration (currently unused beyond indicating
        which columns are timestamps – the timezone metadata is captured from
        :func:`to_timestamp_utc`).

    Returns
    -------
    tuple[list[dict], int, list[AuditRecord], dict[str, str], list[str]]
        ``(records, corrected_count, audit_records, timezone_metadata, warnings)``

        - *corrected_count*:    Number of cells whose value changed after cast.
        - *timezone_metadata*:  ``{column: tz_label}`` for every timestamp column.
        - *warnings*:           Non-fatal conversion failures.
    """
    corrected = 0
    audit_records: List[AuditRecord] = []
    timezone_metadata: Dict[str, str] = {}
    warnings: List[str] = []

    for row_index, record in enumerate(records):
        # ------------------------------------------------------------------
        # Data-type coercion
        # ------------------------------------------------------------------
        for column, target_type in dtypes.items():
            if column not in record:
                continue

            old_value = record[column]
            new_value = old_value

            try:
                if target_type == "integer":
                    new_value = (
                        int(float(old_value))  # type: ignore[arg-type]
                        if old_value not in (None, "")
                        else None
                    )
                elif target_type == "float":
                    new_value = (
                        float(old_value)  # type: ignore[arg-type]
                        if old_value not in (None, "")
                        else None
                    )
                elif target_type == "boolean":
                    new_value = to_bool(old_value)
                elif target_type == "string":
                    new_value = (
                        normalize_text(str(old_value))
                        if old_value is not None
                        else None
                    )
                elif target_type in {"date", "timestamp"}:
                    ts_value, tz_label = to_timestamp_utc(old_value)
                    new_value = ts_value
                    timezone_metadata[column] = tz_label
                    if tz_label == "INVALID":
                        warnings.append(
                            f"Invalid timestamp at row {row_index}, column '{column}'."
                        )
            except (TypeError, ValueError):
                warnings.append(
                    f"Type conversion failed at row {row_index} for column"
                    f" '{column}' → '{target_type}'."
                )
                continue

            if new_value != old_value:
                corrected += 1
                audit_records.append(
                    AuditRecord(
                        dataset=dataset_name,
                        column=column,
                        original_value=old_value,
                        new_value=new_value,
                        cleaning_rule=f"dtype_{target_type}",
                        row_index=row_index,
                    )
                )
                record[column] = new_value

        # ------------------------------------------------------------------
        # Categorical normalisation
        # ------------------------------------------------------------------
        for column, mapping in categoricals.items():
            if column not in record or record[column] is None:
                continue
            original = record[column]
            key = normalize_text(str(original)).lower()
            mapped = mapping.get(key)
            if mapped is not None and mapped != original:
                record[column] = mapped
                audit_records.append(
                    AuditRecord(
                        dataset=dataset_name,
                        column=column,
                        original_value=original,
                        new_value=mapped,
                        cleaning_rule="categorical_mapping",
                        row_index=row_index,
                    )
                )

    return records, corrected, audit_records, timezone_metadata, warnings
