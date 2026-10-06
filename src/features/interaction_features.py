"""Interaction feature engineering for Phase 4.3.

Generates multiplicative interaction terms between pairs of numeric columns.
Interaction features capture non-linear relationships that domain models rely
on (e.g. Temperature × Humidity for comfort, Demand × AQI for impact scoring).

Output column naming
--------------------
``{col_a}_x_{col_b}``
e.g. ``temperature_c_x_humidity``, ``demand_mw_x_aqi``.

Default interactions
--------------------
- ``temperature_c`` × ``humidity``
- ``demand_mw``     × ``temperature_c``
- ``demand_mw``     × ``aqi``
- ``wind_speed``    × ``temperature_c``
- ``rainfall``      × ``demand_mw``

All interactions are fully configurable via :class:`InteractionFeaturesConfig`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.features.feature_metadata import FeatureMetadata

# ---------------------------------------------------------------------------
# Default interaction pairs
# ---------------------------------------------------------------------------

DEFAULT_INTERACTIONS: List[Tuple[str, str]] = [
    ("temperature_c", "humidity"),
    ("demand_mw", "temperature_c"),
    ("demand_mw", "aqi"),
    ("wind_speed", "temperature_c"),
    ("rainfall", "demand_mw"),
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class InteractionFeaturesConfig:
    """Configuration for interaction feature generation.

    Attributes
    ----------
    interactions:
        List of ``(column_a, column_b)`` tuples to multiply together.
    scale:
        Optional global scale factor applied to every interaction product.
        Useful when both inputs have very different magnitudes.
    """

    interactions: List[Tuple[str, str]] = field(
        default_factory=lambda: list(DEFAULT_INTERACTIONS)
    )
    scale: float = 1.0


# ---------------------------------------------------------------------------
# Metadata builder
# ---------------------------------------------------------------------------


def build_interaction_metadata(
    interactions: List[Tuple[str, str]],
    scale: float = 1.0,
) -> List[FeatureMetadata]:
    """Generate :class:`~src.features.feature_metadata.FeatureMetadata` for every interaction.

    Parameters
    ----------
    interactions:
        Column pairs to compute products for.
    scale:
        Scale factor in the formula.

    Returns
    -------
    list[FeatureMetadata]
    """
    metadata: List[FeatureMetadata] = []
    for col_a, col_b in interactions:
        name = f"{col_a}_x_{col_b}"
        scale_note = f" × {scale}" if scale != 1.0 else ""
        metadata.append(
            FeatureMetadata(
                name=name,
                description=f"Multiplicative interaction: {col_a} × {col_b}{scale_note}.",
                formula=f"{col_a} * {col_b}{scale_note}",
                input_columns=[col_a, col_b],
                output_type="float",
                category="interaction",
                unit="",
                tags=["interaction", col_a, col_b],
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


def _interaction_col_name(col_a: str, col_b: str) -> str:
    return f"{col_a}_x_{col_b}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_interaction_features(
    records: List[Dict[str, Any]],
    config: Optional[InteractionFeaturesConfig] = None,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Add multiplicative interaction features to every record.

    Parameters
    ----------
    records:
        Mutable list of record dictionaries (modified in-place).
    config:
        :class:`InteractionFeaturesConfig`.

    Returns
    -------
    tuple[list[dict], list[str], list[str]]
        ``(records, added_columns, warnings)``
    """
    cfg = config or InteractionFeaturesConfig()
    warnings: List[str] = []
    added_set: set[str] = set()

    for row_idx, record in enumerate(records):
        for col_a, col_b in cfg.interactions:
            val_a = _safe_float(record.get(col_a))
            val_b = _safe_float(record.get(col_b))
            feat_name = _interaction_col_name(col_a, col_b)

            if val_a is not None and val_b is not None:
                product = val_a * val_b * cfg.scale
                record[feat_name] = round(product, 6)
            else:
                record[feat_name] = None
                missing = []
                if val_a is None:
                    missing.append(col_a)
                if val_b is None:
                    missing.append(col_b)
                warnings.append(
                    f"Interaction '{feat_name}' skipped at row {row_idx}: "
                    f"missing columns {missing}"
                )
            added_set.add(feat_name)

    added_columns = sorted(added_set)
    return records, added_columns, warnings
