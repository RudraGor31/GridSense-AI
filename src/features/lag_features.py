"""Lag feature engineering for Phase 4.3.

Creates time-shifted copies of numeric columns.  Lag features are foundational
inputs for forecasting models and enable the model to learn temporal patterns.

Supported lag steps (configurable): 1, 3, 6, 12, 24, 48, 168.

Output column naming
--------------------
``{column}_lag_{n}``
e.g. ``demand_mw_lag_1``, ``temperature_c_lag_24``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.features.feature_metadata import FeatureMetadata

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_LAG_STEPS: List[int] = [1, 3, 6, 12, 24, 48, 168]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class LagFeaturesConfig:
    """Configuration for lag feature generation.

    Attributes
    ----------
    columns:
        Numeric columns to generate lag features for.
    lag_steps:
        List of integer lag steps (number of rows to look back).
    fill_value:
        Value to use for the initial rows where look-back exceeds history.
        ``None`` means no fill (the cell is left as ``None``).
    """

    columns: List[str] = field(default_factory=list)
    lag_steps: List[int] = field(default_factory=lambda: list(DEFAULT_LAG_STEPS))
    fill_value: Optional[float] = None


# ---------------------------------------------------------------------------
# Metadata builder
# ---------------------------------------------------------------------------


def build_lag_metadata(
    columns: List[str],
    lag_steps: List[int],
) -> List[FeatureMetadata]:
    """Generate :class:`~src.features.feature_metadata.FeatureMetadata` for every lag feature.

    Parameters
    ----------
    columns:
        Source numeric column names.
    lag_steps:
        Lag step sizes.

    Returns
    -------
    list[FeatureMetadata]
    """
    metadata: List[FeatureMetadata] = []
    for col in columns:
        for lag in lag_steps:
            name = f"{col}_lag_{lag}"
            metadata.append(
                FeatureMetadata(
                    name=name,
                    description=f"Value of '{col}' {lag} rows earlier (lag-{lag}).",
                    formula=f"{col}[t - {lag}]",
                    input_columns=[col],
                    output_type="float",
                    category="lag",
                    unit="",
                    tags=["lag", f"lag_{lag}"],
                )
            )
    return metadata


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_lag_features(
    records: List[Dict[str, Any]],
    config: Optional[LagFeaturesConfig] = None,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Add lag feature columns to every record.

    For a lag of *n*, the value at row *i* is the value from row *i-n*.
    Rows where *i < n* receive ``config.fill_value`` (default ``None``).

    Parameters
    ----------
    records:
        Mutable list of record dictionaries (modified in-place).
    config:
        :class:`LagFeaturesConfig`.

    Returns
    -------
    tuple[list[dict], list[str], list[str]]
        ``(records, added_columns, warnings)``
    """
    cfg = config or LagFeaturesConfig()
    warnings: List[str] = []
    added_set: set[str] = set()

    for col in cfg.columns:
        # Extract the column's values once
        values: List[Any] = [record.get(col) for record in records]

        for lag in cfg.lag_steps:
            feat_name = f"{col}_lag_{lag}"
            for i, record in enumerate(records):
                src_idx = i - lag
                if src_idx >= 0:
                    raw = values[src_idx]
                    if raw is not None and raw != "":
                        try:
                            record[feat_name] = float(raw)  # type: ignore[arg-type]
                        except (TypeError, ValueError):
                            record[feat_name] = cfg.fill_value
                            warnings.append(
                                f"Non-numeric lag source at row {src_idx} for column '{col}'"
                            )
                    else:
                        record[feat_name] = cfg.fill_value
                else:
                    record[feat_name] = cfg.fill_value
                added_set.add(feat_name)

    added_columns = sorted(added_set)
    return records, added_columns, warnings
