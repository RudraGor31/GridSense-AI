"""Energy demand feature engineering for Phase 4.3.

Generates business-relevant energy analytics features from cleaned CEA demand
and supply records.  All features are configuration-driven via
:class:`EnergyFeaturesConfig`.

Generated features
------------------
- ``demand_change_pct``      – Period-over-period % change in demand.
- ``peak_demand_flag``       – True if demand exceeds the configurable peak threshold.
- ``off_peak_flag``          – True if demand is below the off-peak threshold.
- ``load_factor``            – Average demand / peak demand (0-1 ratio).
- ``energy_efficiency_score`` – 0-100 score: high supply coverage, low waste.
- ``demand_supply_gap``      – Absolute gap between demand and supply (MW).
- ``supply_coverage_ratio``  – supply / demand (clipped to [0, 2]).
- ``demand_growth``          – Absolute demand growth vs previous record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.features.feature_metadata import FeatureMetadata

# ---------------------------------------------------------------------------
# Feature metadata
# ---------------------------------------------------------------------------

ENERGY_FEATURE_METADATA: List[FeatureMetadata] = [
    FeatureMetadata(
        name="demand_change_pct",
        description="Percentage change in demand relative to the previous row.",
        formula="(demand[t] - demand[t-1]) / demand[t-1] * 100",
        input_columns=["demand_mw"],
        output_type="float",
        category="energy",
        unit="%",
    ),
    FeatureMetadata(
        name="peak_demand_flag",
        description="True when demand exceeds the configured peak threshold.",
        formula="demand_mw > peak_threshold",
        input_columns=["demand_mw"],
        output_type="bool",
        category="energy",
        unit="",
    ),
    FeatureMetadata(
        name="off_peak_flag",
        description="True when demand is below the configured off-peak threshold.",
        formula="demand_mw < off_peak_threshold",
        input_columns=["demand_mw"],
        output_type="bool",
        category="energy",
        unit="",
    ),
    FeatureMetadata(
        name="load_factor",
        description="Ratio of mean demand to peak demand (dataset window).",
        formula="mean(demand) / max(demand)",
        input_columns=["demand_mw"],
        output_type="float",
        category="energy",
        unit="",
    ),
    FeatureMetadata(
        name="energy_efficiency_score",
        description="0-100 score reflecting supply coverage relative to demand.",
        formula="min(supply_mw / demand_mw, 1) * 100",
        input_columns=["demand_mw", "supply_mw"],
        output_type="float",
        category="energy",
        unit="",
    ),
    FeatureMetadata(
        name="demand_supply_gap",
        description="Absolute gap between demand and supply (positive = deficit).",
        formula="demand_mw - supply_mw",
        input_columns=["demand_mw", "supply_mw"],
        output_type="float",
        category="energy",
        unit="MW",
    ),
    FeatureMetadata(
        name="supply_coverage_ratio",
        description="supply / demand ratio, clipped to [0, 2].",
        formula="min(supply_mw / demand_mw, 2.0)",
        input_columns=["demand_mw", "supply_mw"],
        output_type="float",
        category="energy",
        unit="",
    ),
    FeatureMetadata(
        name="demand_growth",
        description="Absolute demand growth versus previous row (MW).",
        formula="demand[t] - demand[t-1]",
        input_columns=["demand_mw"],
        output_type="float",
        category="energy",
        unit="MW",
    ),
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class EnergyFeaturesConfig:
    """Configuration for energy feature generation.

    Attributes
    ----------
    demand_column:
        Column holding energy demand in MW.
    supply_column:
        Column holding energy supply in MW.
    peak_threshold:
        Demand MW value above which ``peak_demand_flag`` is True.
    off_peak_threshold:
        Demand MW value below which ``off_peak_flag`` is True.
    """

    demand_column: str = "demand_mw"
    supply_column: str = "supply_mw"
    peak_threshold: float = 150000.0
    off_peak_threshold: float = 80000.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _compute_load_factor(demands: List[float]) -> Optional[float]:
    if not demands:
        return None
    peak = max(demands)
    if peak == 0.0:
        return None
    return round(sum(demands) / len(demands) / peak, 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_energy_features(
    records: List[Dict[str, Any]],
    config: Optional[EnergyFeaturesConfig] = None,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Add energy business features to every record.

    A first pass collects all demand values to compute the global load factor;
    a second pass writes per-row features.

    Parameters
    ----------
    records:
        Mutable list of record dictionaries (modified in-place).
    config:
        :class:`EnergyFeaturesConfig`.  Defaults to column-name defaults.

    Returns
    -------
    tuple[list[dict], list[str], list[str]]
        ``(records, added_columns, warnings)``
    """
    cfg = config or EnergyFeaturesConfig()
    warnings: List[str] = []

    # First pass – collect numeric demand values for load_factor
    demands: List[float] = []
    for record in records:
        d = _safe_float(record.get(cfg.demand_column))
        if d is not None:
            demands.append(d)

    global_load_factor = _compute_load_factor(demands)

    # Second pass – per-row features
    prev_demand: Optional[float] = None

    for row_idx, record in enumerate(records):
        demand = _safe_float(record.get(cfg.demand_column))
        supply = _safe_float(record.get(cfg.supply_column))

        # demand_change_pct
        if demand is not None and prev_demand is not None and prev_demand != 0.0:
            record["demand_change_pct"] = round(
                (demand - prev_demand) / prev_demand * 100.0, 4
            )
        else:
            record["demand_change_pct"] = None
            if row_idx > 0 and demand is None:
                warnings.append(
                    f"demand_change_pct skipped at row {row_idx}: missing demand"
                )

        # peak / off-peak flags
        if demand is not None:
            record["peak_demand_flag"] = demand > cfg.peak_threshold
            record["off_peak_flag"] = demand < cfg.off_peak_threshold
        else:
            record["peak_demand_flag"] = None
            record["off_peak_flag"] = None

        # load_factor (same value for all rows in this window)
        record["load_factor"] = global_load_factor

        # energy_efficiency_score
        if demand is not None and supply is not None and demand > 0.0:
            ratio = min(supply / demand, 1.0)
            record["energy_efficiency_score"] = round(ratio * 100.0, 2)
        else:
            record["energy_efficiency_score"] = None

        # demand_supply_gap
        if demand is not None and supply is not None:
            record["demand_supply_gap"] = round(demand - supply, 4)
        else:
            record["demand_supply_gap"] = None

        # supply_coverage_ratio
        if demand is not None and supply is not None and demand > 0.0:
            record["supply_coverage_ratio"] = round(min(supply / demand, 2.0), 4)
        else:
            record["supply_coverage_ratio"] = None

        # demand_growth
        if demand is not None and prev_demand is not None:
            record["demand_growth"] = round(demand - prev_demand, 4)
        else:
            record["demand_growth"] = None

        prev_demand = demand

    added_columns = [
        "demand_change_pct",
        "peak_demand_flag",
        "off_peak_flag",
        "load_factor",
        "energy_efficiency_score",
        "demand_supply_gap",
        "supply_coverage_ratio",
        "demand_growth",
    ]
    return records, added_columns, warnings
