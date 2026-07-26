"""Time-based feature generation for Phase 4.3.

Extracts temporal features from a configurable timestamp column.  All features
are derived using the Python standard library ``datetime`` module — no external
dependencies required.

Generated features
------------------
- ``year``              – Calendar year (int)
- ``quarter``           – Calendar quarter 1-4 (int)
- ``month``             – Month number 1-12 (int)
- ``month_name``        – Month name e.g. ``"January"`` (str)
- ``week_of_year``      – ISO week number 1-53 (int)
- ``day_of_month``      – Day within month 1-31 (int)
- ``day_of_week``       – ISO weekday 1 (Mon) – 7 (Sun) (int)
- ``day_name``          – Day name e.g. ``"Monday"`` (str)
- ``is_weekend``        – True if Sat or Sun (bool)
- ``is_business_day``   – True if Mon-Fri (bool)
- ``hour``              – Hour of day 0-23 (int)
- ``minute``            – Minute 0-59 (int)
- ``season``            – One of ``"Spring"``, ``"Summer"``, ``"Autumn"``, ``"Winter"`` (str)
- ``financial_quarter`` – FY quarter based on April-March cycle (int)
- ``is_holiday``        – Configurable holiday flag (bool); always False unless
                          holiday dates are supplied via configuration.
- ``time_of_day``       – Categorical: ``"Night"``, ``"Morning"``,
                          ``"Afternoon"``, ``"Evening"`` (str)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from src.features.feature_metadata import FeatureMetadata
from src.features.feature_registry import registry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]

# Northern-hemisphere seasons (month-based approximation)
_SEASONS: List[Tuple[str, Set[int]]] = [
    ("Spring", {3, 4, 5}),
    ("Summer", {6, 7, 8}),
    ("Autumn", {9, 10, 11}),
    ("Winter", {12, 1, 2}),
]

# Time-of-day buckets (hour boundaries are inclusive lower bound)
_TIME_BUCKETS: List[Tuple[str, int, int]] = [
    ("Night",     0,  5),
    ("Morning",   6, 11),
    ("Afternoon", 12, 16),
    ("Evening",   17, 21),
    ("Night",     22, 23),
]

# ---------------------------------------------------------------------------
# Metadata registration
# ---------------------------------------------------------------------------

_TIME_METADATA: List[FeatureMetadata] = [
    FeatureMetadata(
        name="year", description="Calendar year", formula="datetime.year",
        input_columns=["timestamp"], output_type="int", category="time",
        valid_min=2000, valid_max=2100,
    ),
    FeatureMetadata(
        name="quarter", description="Calendar quarter (1-4)",
        formula="ceil(month / 3)", input_columns=["timestamp"],
        output_type="int", category="time", valid_min=1, valid_max=4,
    ),
    FeatureMetadata(
        name="month", description="Month number (1-12)",
        formula="datetime.month", input_columns=["timestamp"],
        output_type="int", category="time", valid_min=1, valid_max=12,
    ),
    FeatureMetadata(
        name="month_name", description="Full month name",
        formula="MONTH_NAMES[month - 1]", input_columns=["timestamp"],
        output_type="str", category="time",
    ),
    FeatureMetadata(
        name="week_of_year", description="ISO week number (1-53)",
        formula="datetime.isocalendar().week", input_columns=["timestamp"],
        output_type="int", category="time", valid_min=1, valid_max=53,
    ),
    FeatureMetadata(
        name="day_of_month", description="Day of month (1-31)",
        formula="datetime.day", input_columns=["timestamp"],
        output_type="int", category="time", valid_min=1, valid_max=31,
    ),
    FeatureMetadata(
        name="day_of_week", description="ISO weekday (1=Mon, 7=Sun)",
        formula="datetime.isoweekday()", input_columns=["timestamp"],
        output_type="int", category="time", valid_min=1, valid_max=7,
    ),
    FeatureMetadata(
        name="day_name", description="Full day name",
        formula="DAY_NAMES[weekday - 1]", input_columns=["timestamp"],
        output_type="str", category="time",
    ),
    FeatureMetadata(
        name="is_weekend", description="True if Saturday or Sunday",
        formula="day_of_week >= 6", input_columns=["timestamp"],
        output_type="bool", category="time",
    ),
    FeatureMetadata(
        name="is_business_day", description="True if Monday-Friday",
        formula="day_of_week <= 5", input_columns=["timestamp"],
        output_type="bool", category="time",
    ),
    FeatureMetadata(
        name="hour", description="Hour of day (0-23)",
        formula="datetime.hour", input_columns=["timestamp"],
        output_type="int", category="time", valid_min=0, valid_max=23,
    ),
    FeatureMetadata(
        name="minute", description="Minute of hour (0-59)",
        formula="datetime.minute", input_columns=["timestamp"],
        output_type="int", category="time", valid_min=0, valid_max=59,
    ),
    FeatureMetadata(
        name="season", description="Northern-hemisphere meteorological season",
        formula="Spring|Summer|Autumn|Winter based on month",
        input_columns=["timestamp"], output_type="str", category="time",
    ),
    FeatureMetadata(
        name="financial_quarter",
        description="Financial year quarter (April-March cycle, Q1=Apr-Jun)",
        formula="((month - 4) % 12) // 3 + 1",
        input_columns=["timestamp"], output_type="int", category="time",
        valid_min=1, valid_max=4,
    ),
    FeatureMetadata(
        name="is_holiday",
        description="True if the date is in the configured holiday set",
        formula="date in holiday_dates", input_columns=["timestamp"],
        output_type="bool", category="time",
    ),
    FeatureMetadata(
        name="time_of_day",
        description="Categorical time bucket: Night/Morning/Afternoon/Evening",
        formula="bucket(hour)", input_columns=["timestamp"],
        output_type="str", category="time",
    ),
]


def _register_metadata() -> None:
    registry.register_many(_TIME_METADATA)


_register_metadata()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse a timestamp value to a :class:`datetime` in UTC.

    Parameters
    ----------
    value:
        ISO-8601 string, Unix epoch float, or ``datetime`` object.

    Returns
    -------
    datetime | None
        Timezone-aware UTC datetime, or ``None`` if unparseable.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        candidate = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _season(month: int) -> str:
    for name, months in _SEASONS:
        if month in months:
            return name
    return "Unknown"


def _financial_quarter(month: int) -> int:
    """April-March financial year: April=Q1, July=Q2, Oct=Q3, Jan=Q4."""
    return ((month - 4) % 12) // 3 + 1


def _time_of_day(hour: int) -> str:
    for label, low, high in _TIME_BUCKETS:
        if low <= hour <= high:
            return label
    return "Unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_time_features(
    records: List[Dict[str, Any]],
    timestamp_column: str = "timestamp",
    holiday_dates: Optional[Set[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Add temporal features to every record in *records*.

    Parameters
    ----------
    records:
        Mutable list of record dictionaries (modified in-place).
    timestamp_column:
        Name of the column containing the timestamp value.
    holiday_dates:
        Set of ISO date strings (``"YYYY-MM-DD"``) treated as holidays.
        If ``None`` or empty, ``is_holiday`` is always ``False``.

    Returns
    -------
    tuple[list[dict], list[str]]
        ``(records, warnings)``

        - *records*: The same list, enriched with time features.
        - *warnings*: Non-fatal issues (e.g. unparseable timestamps).
    """
    holidays: Set[str] = holiday_dates or set()
    warnings: List[str] = []

    for row_index, record in enumerate(records):
        raw = record.get(timestamp_column)
        dt = _parse_timestamp(raw)
        if dt is None:
            warnings.append(
                f"Cannot parse timestamp at row {row_index}: {raw!r}."
                f" Time features set to None."
            )
            _set_null_time_features(record)
            continue

        month = dt.month
        dow = dt.isoweekday()  # 1=Mon, 7=Sun

        record["year"] = dt.year
        record["quarter"] = (month - 1) // 3 + 1
        record["month"] = month
        record["month_name"] = _MONTH_NAMES[month - 1]
        record["week_of_year"] = dt.isocalendar()[1]
        record["day_of_month"] = dt.day
        record["day_of_week"] = dow
        record["day_name"] = _DAY_NAMES[dow - 1]
        record["is_weekend"] = dow >= 6
        record["is_business_day"] = dow <= 5
        record["hour"] = dt.hour
        record["minute"] = dt.minute
        record["season"] = _season(month)
        record["financial_quarter"] = _financial_quarter(month)
        record["is_holiday"] = dt.strftime("%Y-%m-%d") in holidays
        record["time_of_day"] = _time_of_day(dt.hour)

    return records, warnings


def _set_null_time_features(record: Dict[str, Any]) -> None:
    """Set all time features to ``None`` for rows with unparseable timestamps."""
    for col in [
        "year", "quarter", "month", "month_name", "week_of_year",
        "day_of_month", "day_of_week", "day_name", "is_weekend",
        "is_business_day", "hour", "minute", "season", "financial_quarter",
        "is_holiday", "time_of_day",
    ]:
        record[col] = None
