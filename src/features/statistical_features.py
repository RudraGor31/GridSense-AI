"""Statistical feature engineering for Phase 4.3.

Computes dataset-level and per-row statistical features from numeric columns.

Generated features (per column)
--------------------------------
- ``{col}_mean``         – Arithmetic mean over all records.
- ``{col}_median``       – Median over all records.
- ``{col}_variance``     – Population variance over all records.
- ``{col}_std``          – Population standard deviation.
- ``{col}_cv``           – Coefficient of variation (std/mean × 100 %).
- ``{col}_pct_change``   – Per-row percentage change vs previous row.
- ``{col}_moving_avg``   – Simple moving average with a configurable span.
- ``{col}_cumsum``       – Cumulative sum up to and including the current row.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean, median, pvariance, pstdev
from typing import Any, Dict, List, Optional, Tuple

from src.features.feature_metadata import FeatureMetadata

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class StatisticalFeaturesConfig:
    """Configuration for statistical feature generation.

    Attributes
    ----------
    columns:
        Numeric columns to generate statistical features for.
    moving_avg_span:
        Window size for the simple moving average.
    enabled_features:
        Subset of feature slugs to generate.  ``None`` means all.
    """

    columns: List[str] = field(default_factory=list)
    moving_avg_span: int = 7
    enabled_features: Optional[List[str]] = None


# Canonical slug list for the enabled_features filter
_ALL_STAT_SLUGS = [
    "mean",
    "median",
    "variance",
    "std",
    "cv",
    "pct_change",
    "moving_avg",
    "cumsum",
]


# ---------------------------------------------------------------------------
# Metadata builder
# ---------------------------------------------------------------------------


def build_statistical_metadata(
    columns: List[str],
    moving_avg_span: int = 7,
) -> List[FeatureMetadata]:
    """Generate feature metadata for every statistical feature.

    Parameters
    ----------
    columns:
        Source numeric column names.
    moving_avg_span:
        Moving average window size.

    Returns
    -------
    list[FeatureMetadata]
    """
    metadata: List[FeatureMetadata] = []
    descriptors = [
        ("mean", "Arithmetic mean over all records.", "mean(col)", "float", ""),
        ("median", "Median over all records.", "median(col)", "float", ""),
        (
            "variance",
            "Population variance over all records.",
            "pvariance(col)",
            "float",
            "",
        ),
        (
            "std",
            "Population standard deviation over all records.",
            "pstdev(col)",
            "float",
            "",
        ),
        (
            "cv",
            "Coefficient of variation (std / mean × 100).",
            "std/mean*100",
            "float",
            "%",
        ),
        (
            "pct_change",
            "Per-row percentage change vs previous row.",
            "(col[t]-col[t-1])/col[t-1]*100",
            "float",
            "%",
        ),
        (
            "moving_avg",
            f"Simple moving average with span={moving_avg_span}.",
            f"mean(col[t-{moving_avg_span}:t])",
            "float",
            "",
        ),
        (
            "cumsum",
            "Cumulative sum up to and including the current row.",
            "sum(col[0:t+1])",
            "float",
            "",
        ),
    ]
    for col in columns:
        for slug, desc, formula, out_type, unit in descriptors:
            metadata.append(
                FeatureMetadata(
                    name=f"{col}_{slug}",
                    description=f"{desc} (column: {col})",
                    formula=formula.replace("col", col),
                    input_columns=[col],
                    output_type=out_type,
                    category="statistical",
                    unit=unit,
                    tags=["statistical", slug],
                )
            )
    return metadata


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


def _numeric_values(records: List[Dict[str, Any]], col: str) -> List[float]:
    """Extract all non-None numeric values for *col* across all records."""
    result: List[float] = []
    for record in records:
        v = _safe_float(record.get(col))
        if v is not None:
            result.append(v)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_statistical_features(
    records: List[Dict[str, Any]],
    config: Optional[StatisticalFeaturesConfig] = None,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Add statistical feature columns to every record.

    Global statistics (mean, median, variance, std, cv) are computed once
    over the entire dataset and written as a constant into every row.
    Per-row statistics (pct_change, moving_avg, cumsum) are computed
    incrementally.

    Parameters
    ----------
    records:
        Mutable list of record dictionaries (modified in-place).
    config:
        :class:`StatisticalFeaturesConfig`.

    Returns
    -------
    tuple[list[dict], list[str], list[str]]
        ``(records, added_columns, warnings)``
    """
    cfg = config or StatisticalFeaturesConfig()
    enabled = (
        set(cfg.enabled_features) if cfg.enabled_features else set(_ALL_STAT_SLUGS)
    )
    warnings: List[str] = []
    added_set: set[str] = set()

    for col in cfg.columns:
        all_vals = _numeric_values(records, col)

        # -- Global stats (computed once) --
        global_mean: Optional[float] = None
        global_median: Optional[float] = None
        global_variance: Optional[float] = None
        global_std: Optional[float] = None
        global_cv: Optional[float] = None

        if len(all_vals) >= 1:
            global_mean = round(mean(all_vals), 6)
            global_median = round(median(all_vals), 6)
        if len(all_vals) >= 2:
            global_variance = round(pvariance(all_vals), 6)
            global_std = round(pstdev(all_vals), 6)
            if global_mean and global_mean != 0.0:
                global_cv = round(global_std / global_mean * 100.0, 4)
        elif len(all_vals) == 1:
            global_variance = 0.0
            global_std = 0.0
            global_cv = 0.0

        # -- Per-row computation --
        prev_val: Optional[float] = None
        cumsum: float = 0.0

        for row_idx, record in enumerate(records):
            current = _safe_float(record.get(col))
            if current is not None:
                cumsum += current

            # Global statistics written as constants
            if "mean" in enabled:
                record[f"{col}_mean"] = global_mean
                added_set.add(f"{col}_mean")
            if "median" in enabled:
                record[f"{col}_median"] = global_median
                added_set.add(f"{col}_median")
            if "variance" in enabled:
                record[f"{col}_variance"] = global_variance
                added_set.add(f"{col}_variance")
            if "std" in enabled:
                record[f"{col}_std"] = global_std
                added_set.add(f"{col}_std")
            if "cv" in enabled:
                record[f"{col}_cv"] = global_cv
                added_set.add(f"{col}_cv")

            # pct_change
            if "pct_change" in enabled:
                if current is not None and prev_val is not None and prev_val != 0.0:
                    record[f"{col}_pct_change"] = round(
                        (current - prev_val) / prev_val * 100.0, 4
                    )
                else:
                    record[f"{col}_pct_change"] = None
                added_set.add(f"{col}_pct_change")

            # moving_avg
            if "moving_avg" in enabled:
                start = max(0, row_idx - cfg.moving_avg_span + 1)
                window: List[float] = []
                for r in records[start : row_idx + 1]:
                    v = _safe_float(r.get(col))
                    if v is not None:
                        window.append(v)
                record[f"{col}_moving_avg"] = round(mean(window), 6) if window else None
                added_set.add(f"{col}_moving_avg")

            # cumsum
            if "cumsum" in enabled:
                record[f"{col}_cumsum"] = (
                    round(cumsum, 6) if current is not None else None
                )
                added_set.add(f"{col}_cumsum")

            prev_val = current

    added_columns = sorted(added_set)
    return records, added_columns, warnings
