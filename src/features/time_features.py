"""Time-based feature engineering for Phase 4.3.

Derives calendar and cyclical temporal features from an ISO-8601 UTC timestamp
column.  All features are configuration-driven — the column name and which
features to generate are specified via :class:`TimeFeaturesConfig`.

Generated features
------------------
- ``year``              – 4-digit year (int)
- ``quarter``           – Calendar quarter 1-4 (int)
- ``month``             – Month 1-12 (int)
- ``month_name``        – Full English month name (str)
- ``week``              – ISO week number 1-53 (int)
- ``day``               – Day of month 1-31 (int)
- ``day_of_week``       – Day of week 0=Mon … 6=Sun (int)
- ``day_name``          – Full English day name (str)
- ``is_weekend``        – True if Sat or Sun (bool)
- ``is_business_day``   – True if Mon-Fri (bool)
- ``is_holiday``        – True if date appears in the holidays set (bool)
- ``hour``              – Hour 0-23 (int)
- ``minute``            – Minute 0-59 (int)
- ``season``            – "Spring" / "Summer" / "Autumn" / "Winter" (Northern Hemisphere) (str)
- ``financial_quarter`` – Financial quarter label "Q1"-"Q4" based on April fiscal year start (str)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.features.feature_metadata import FeatureMetadata

# ---------------------------------------------------------------------------
# Season & financial-quarter lookup tables
# ---------------------------------------------------------------------------

_MONTH_TO_SEASON: Dict[int, str] = {
    1: "Winter",
    2: "Winter",
    3: "Spring",
    4: "Spring",
    5: "Spring",
    6: "Summer",
    7: "Summer",
    8: "Summer",
    9: "Autumn",
    10: "Autumn",
    11: "Autumn",
    12: "Winter",
}

# India / Germany fiscal year starts April 1
_MONTH_TO_FIN_QUARTER: Dict[int, str] = {
    4: "Q1",
    5: "Q1",
    6: "Q1",
    7: "Q2",
    8: "Q2",
    9: "Q2",
    10: "Q3",
    11: "Q3",
    12: "Q3",
    1: "Q4",
    2: "Q4",
    3: "Q4",
}

_MONTH_NAMES = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

_DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class TimeFeaturesConfig:
    """Configuration for time feature generation.

    Attributes
    ----------
    timestamp_column:
        Name of the source timestamp column (ISO-8601 UTC string).
    enabled_features:
        Set of feature slugs to generate.  ``None`` means *all* features.
    holidays:
        Set of date strings in ``"YYYY-MM-DD"`` format treated as public holidays.
    """

    timestamp_column: str = "timestamp"
    enabled_features: Optional[Set[str]] = None
    holidays: Set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

#: All feature metadata descriptors provided by this module.
TIME_FEATURE_METADATA: List[FeatureMetadata] = [
    FeatureMetadata(
        name="year",
        description="Calendar year extracted from the timestamp.",
        formula="datetime.year",
        input_columns=["timestamp"],
        output_type="int",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="quarter",
        description="Calendar quarter (1-4) extracted from the timestamp.",
        formula="ceil(month / 3)",
        input_columns=["timestamp"],
        output_type="int",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="month",
        description="Calendar month (1-12).",
        formula="datetime.month",
        input_columns=["timestamp"],
        output_type="int",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="month_name",
        description="Full English name of the month.",
        formula="MONTH_NAMES[month]",
        input_columns=["timestamp"],
        output_type="str",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="week",
        description="ISO week number (1-53).",
        formula="datetime.isocalendar().week",
        input_columns=["timestamp"],
        output_type="int",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="day",
        description="Day of the month (1-31).",
        formula="datetime.day",
        input_columns=["timestamp"],
        output_type="int",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="day_of_week",
        description="Day of week (0=Monday … 6=Sunday).",
        formula="datetime.weekday()",
        input_columns=["timestamp"],
        output_type="int",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="day_name",
        description="Full English name of the day.",
        formula="DAY_NAMES[weekday]",
        input_columns=["timestamp"],
        output_type="str",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="is_weekend",
        description="True if the day is Saturday or Sunday.",
        formula="weekday >= 5",
        input_columns=["timestamp"],
        output_type="bool",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="is_business_day",
        description="True if the day is Monday through Friday.",
        formula="weekday < 5",
        input_columns=["timestamp"],
        output_type="bool",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="is_holiday",
        description="True if the date appears in the configured holiday set.",
        formula="date_str in holidays",
        input_columns=["timestamp"],
        output_type="bool",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="hour",
        description="Hour of the day (0-23).",
        formula="datetime.hour",
        input_columns=["timestamp"],
        output_type="int",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="minute",
        description="Minute of the hour (0-59).",
        formula="datetime.minute",
        input_columns=["timestamp"],
        output_type="int",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="season",
        description="Meteorological season (Northern Hemisphere).",
        formula="MONTH_TO_SEASON[month]",
        input_columns=["timestamp"],
        output_type="str",
        category="time",
        unit="",
    ),
    FeatureMetadata(
        name="financial_quarter",
        description="Financial quarter label (April fiscal-year start).",
        formula="MONTH_TO_FIN_QUARTER[month]",
        input_columns=["timestamp"],
        output_type="str",
        category="time",
        unit="",
    ),
]

_ALL_TIME_FEATURES = {m.name for m in TIME_FEATURE_METADATA}


def _parse_utc(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 string to a UTC-aware datetime.

    Parameters
    ----------
    value:
        Raw timestamp value from the record.

    Returns
    -------
    datetime | None
        ``None`` if the value cannot be parsed.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    try:
        candidate = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(candidate)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def add_time_features(
    records: List[Dict[str, Any]],
    config: Optional[TimeFeaturesConfig] = None,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Add time-based feature columns to every record.

    Parameters
    ----------
    records:
        Mutable list of record dictionaries (modified in-place).
    config:
        :class:`TimeFeaturesConfig` instance.  Defaults to
        ``TimeFeaturesConfig()`` (all features, column ``"timestamp"``).

    Returns
    -------
    tuple[list[dict], list[str], list[str]]
        ``(records, added_columns, warnings)``
    """
    cfg = config or TimeFeaturesConfig()
    enabled = cfg.enabled_features or _ALL_TIME_FEATURES
    added_columns: List[str] = []
    warnings: List[str] = []
    col = cfg.timestamp_column

    for row_idx, record in enumerate(records):
        raw = record.get(col)
        dt = _parse_utc(raw)

        if dt is None:
            if raw is not None:
                warnings.append(f"Could not parse timestamp at row {row_idx}: {raw!r}")
            # Write None for all enabled features so the row is complete
            for feat in sorted(enabled):
                if feat not in record:
                    record[feat] = None
                    if feat not in added_columns:
                        added_columns.append(feat)
            continue

        weekday = dt.weekday()
        month = dt.month
        date_str = dt.strftime("%Y-%m-%d")

        feature_map: Dict[str, Any] = {
            "year": dt.year,
            "quarter": (month - 1) // 3 + 1,
            "month": month,
            "month_name": _MONTH_NAMES[month],
            "week": dt.isocalendar()[1],
            "day": dt.day,
            "day_of_week": weekday,
            "day_name": _DAY_NAMES[weekday],
            "is_weekend": weekday >= 5,
            "is_business_day": weekday < 5,
            "is_holiday": date_str in cfg.holidays,
            "hour": dt.hour,
            "minute": dt.minute,
            "season": _MONTH_TO_SEASON[month],
            "financial_quarter": _MONTH_TO_FIN_QUARTER[month],
        }

        for feat, val in feature_map.items():
            if feat in enabled:
                record[feat] = val
                if feat not in added_columns:
                    added_columns.append(feat)

    return records, added_columns, warnings


# Re-export Tuple for callers that use it from this module
from typing import Tuple  # noqa: E402
