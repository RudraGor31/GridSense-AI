"""Air quality feature engineering for Phase 4.3.

Derives public-health-relevant features from cleaned WAQI AQI records.
All thresholds follow the US EPA AQI standard breakpoints.

Generated features
------------------
- ``aqi_category``         – "Good" / "Moderate" / "USG" / "Unhealthy" / "Very Unhealthy" / "Hazardous".
- ``pollution_level``      – Numeric severity tier 1-6 matching the AQI category.
- ``aqi_change``           – Change in AQI vs previous row.
- ``aqi_trend``            – "Improving" / "Stable" / "Worsening".
- ``aqi_severity_score``   – 0-100 normalised AQI severity (AQI/500 × 100).
- ``safe_exposure``        – True if AQI < 100 (Good or Moderate = generally safe outdoors).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.features.feature_metadata import FeatureMetadata

# ---------------------------------------------------------------------------
# Feature metadata
# ---------------------------------------------------------------------------

AQI_FEATURE_METADATA: List[FeatureMetadata] = [
    FeatureMetadata(
        name="aqi_category",
        description="US EPA AQI category label.",
        formula="Good(<51)|Moderate(51-100)|USG(101-150)|Unhealthy(151-200)|Very Unhealthy(201-300)|Hazardous(>300)",
        input_columns=["aqi"],
        output_type="str",
        category="air_quality",
        unit="",
    ),
    FeatureMetadata(
        name="pollution_level",
        description="Numeric pollution tier 1=Good … 6=Hazardous.",
        formula="tier(aqi_category)",
        input_columns=["aqi"],
        output_type="int",
        category="air_quality",
        unit="",
    ),
    FeatureMetadata(
        name="aqi_change",
        description="Change in AQI index versus the previous record.",
        formula="aqi[t] - aqi[t-1]",
        input_columns=["aqi"],
        output_type="float",
        category="air_quality",
        unit="",
    ),
    FeatureMetadata(
        name="aqi_trend",
        description="Direction of AQI change: Improving / Stable / Worsening.",
        formula="sign(aqi_change): <-5 Improving | >5 Worsening | else Stable",
        input_columns=["aqi"],
        output_type="str",
        category="air_quality",
        unit="",
    ),
    FeatureMetadata(
        name="aqi_severity_score",
        description="0-100 normalised AQI severity (AQI/500 × 100, capped at 100).",
        formula="min(aqi / 500.0, 1.0) * 100",
        input_columns=["aqi"],
        output_type="float",
        category="air_quality",
        unit="",
    ),
    FeatureMetadata(
        name="safe_exposure",
        description="True when outdoor exposure is generally safe (AQI < 100).",
        formula="aqi < 100",
        input_columns=["aqi"],
        output_type="bool",
        category="air_quality",
        unit="",
    ),
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class AQIFeaturesConfig:
    """Configuration for AQI feature generation.

    Attributes
    ----------
    aqi_column:
        Column holding the AQI index value.
    trend_threshold:
        Absolute AQI change beyond which the trend is "Improving" or "Worsening"
        (default 5).
    safe_threshold:
        AQI value below which ``safe_exposure`` is True (default 100).
    """

    aqi_column: str = "aqi"
    trend_threshold: float = 5.0
    safe_threshold: float = 100.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _aqi_category(aqi: float) -> str:
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"


def _pollution_level(aqi: float) -> int:
    if aqi <= 50:
        return 1
    if aqi <= 100:
        return 2
    if aqi <= 150:
        return 3
    if aqi <= 200:
        return 4
    if aqi <= 300:
        return 5
    return 6


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_aqi_features(
    records: List[Dict[str, Any]],
    config: Optional[AQIFeaturesConfig] = None,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Add air-quality feature columns to every record.

    Parameters
    ----------
    records:
        Mutable list of record dictionaries (modified in-place).
    config:
        :class:`AQIFeaturesConfig`.  Defaults to column-name defaults.

    Returns
    -------
    tuple[list[dict], list[str], list[str]]
        ``(records, added_columns, warnings)``
    """
    cfg = config or AQIFeaturesConfig()
    warnings: List[str] = []
    prev_aqi: Optional[float] = None

    for row_idx, record in enumerate(records):
        aqi_val = _safe_float(record.get(cfg.aqi_column))

        if aqi_val is not None:
            record["aqi_category"] = _aqi_category(aqi_val)
            record["pollution_level"] = _pollution_level(aqi_val)
            record["aqi_severity_score"] = round(min(aqi_val / 500.0, 1.0) * 100.0, 2)
            record["safe_exposure"] = aqi_val < cfg.safe_threshold
        else:
            record["aqi_category"] = None
            record["pollution_level"] = None
            record["aqi_severity_score"] = None
            record["safe_exposure"] = None
            warnings.append(f"AQI features skipped at row {row_idx}: missing aqi value")

        # aqi_change and aqi_trend
        if aqi_val is not None and prev_aqi is not None:
            change = aqi_val - prev_aqi
            record["aqi_change"] = round(change, 2)
            if change < -cfg.trend_threshold:
                record["aqi_trend"] = "Improving"
            elif change > cfg.trend_threshold:
                record["aqi_trend"] = "Worsening"
            else:
                record["aqi_trend"] = "Stable"
        else:
            record["aqi_change"] = None
            record["aqi_trend"] = None

        prev_aqi = aqi_val

    added_columns = [
        "aqi_category",
        "pollution_level",
        "aqi_change",
        "aqi_trend",
        "aqi_severity_score",
        "safe_exposure",
    ]
    return records, added_columns, warnings
