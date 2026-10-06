"""Rolling window feature engineering for Phase 4.3.

Computes sliding-window aggregations (mean, median, std, min, max, sum) over
configurable window sizes.  All computations use pure Python — no external
dependencies.

Supported window sizes (configurable): 3, 6, 12, 24, 48, 168.
Supported aggregations: mean, median, std, min, max, sum.

Output column naming
--------------------
``{column}_rolling_{window}_{agg}``
e.g. ``demand_mw_rolling_24_mean``, ``temperature_c_rolling_6_std``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean, median, pstdev
from typing import Any, Dict, List, Optional, Tuple

from src.features.feature_metadata import FeatureMetadata

# ---------------------------------------------------------------------------
# Default window sizes and aggregations
# ---------------------------------------------------------------------------

DEFAULT_WINDOWS: List[int] = [3, 6, 12, 24, 48, 168]
DEFAULT_AGGREGATIONS: List[str] = ["mean", "median", "std", "min", "max", "sum"]

SUPPORTED_AGGREGATIONS = frozenset(DEFAULT_AGGREGATIONS)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class RollingFeaturesConfig:
    """Configuration for rolling window features.

    Attributes
    ----------
    columns:
        Numeric columns to compute rolling features for.
    windows:
        List of window sizes (number of preceding rows).
    aggregations:
        List of aggregation functions to apply.
    min_periods:
        Minimum number of non-None observations required for a valid result.
        If fewer observations are available the output is ``None``.
    """

    columns: List[str] = field(default_factory=list)
    windows: List[int] = field(default_factory=lambda: list(DEFAULT_WINDOWS))
    aggregations: List[str] = field(default_factory=lambda: list(DEFAULT_AGGREGATIONS))
    min_periods: int = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _rolling_agg(values: List[float], agg: str) -> Optional[float]:
    """Apply *agg* to *values*, returning ``None`` if values is empty."""
    if not values:
        return None
    if agg == "mean":
        return round(mean(values), 6)
    if agg == "median":
        return round(median(values), 6)
    if agg == "std":
        if len(values) < 2:
            return None
        return round(pstdev(values), 6)
    if agg == "min":
        return round(min(values), 6)
    if agg == "max":
        return round(max(values), 6)
    if agg == "sum":
        return round(sum(values), 6)
    return None


def build_rolling_metadata(
    columns: List[str],
    windows: List[int],
    aggregations: List[str],
) -> List[FeatureMetadata]:
    """Generate :class:`~src.features.feature_metadata.FeatureMetadata` for every rolling feature.

    Parameters
    ----------
    columns:
        Source numeric column names.
    windows:
        Window sizes.
    aggregations:
        Aggregation function names.

    Returns
    -------
    list[FeatureMetadata]
    """
    metadata: List[FeatureMetadata] = []
    for col in columns:
        for win in windows:
            for agg in aggregations:
                name = f"{col}_rolling_{win}_{agg}"
                metadata.append(
                    FeatureMetadata(
                        name=name,
                        description=f"Rolling {agg} of '{col}' over the last {win} observations.",
                        formula=f"{agg}({col}[t-{win}:t])",
                        input_columns=[col],
                        output_type="float",
                        category="rolling",
                        unit="",
                        tags=["rolling", agg, f"window_{win}"],
                    )
                )
    return metadata


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_rolling_features(
    records: List[Dict[str, Any]],
    config: Optional[RollingFeaturesConfig] = None,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Add rolling window aggregation features to every record.

    Parameters
    ----------
    records:
        Mutable list of record dictionaries (modified in-place).
    config:
        :class:`RollingFeaturesConfig`.

    Returns
    -------
    tuple[list[dict], list[str], list[str]]
        ``(records, added_columns, warnings)``
    """
    cfg = config or RollingFeaturesConfig()
    warnings: List[str] = []
    added_set: set[str] = set()

    invalid_aggs = [a for a in cfg.aggregations if a not in SUPPORTED_AGGREGATIONS]
    if invalid_aggs:
        warnings.append(f"Unsupported aggregations will be skipped: {invalid_aggs}")

    valid_aggs = [a for a in cfg.aggregations if a in SUPPORTED_AGGREGATIONS]

    for col in cfg.columns:
        # Collect numeric history per column
        history: List[Optional[float]] = []
        for row_idx, record in enumerate(records):
            current = _safe_float(record.get(col))
            history.append(current)

            for win in cfg.windows:
                # Slice the look-back window (not including current row)
                start = max(0, row_idx - win + 1)
                window_vals = [v for v in history[start : row_idx + 1] if v is not None]

                for agg in valid_aggs:
                    feat_name = f"{col}_rolling_{win}_{agg}"
                    if len(window_vals) >= cfg.min_periods:
                        record[feat_name] = _rolling_agg(window_vals, agg)
                    else:
                        record[feat_name] = None
                    added_set.add(feat_name)

    added_columns = sorted(added_set)
    return records, added_columns, warnings
