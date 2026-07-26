"""Config-driven cleaning rule definitions for Phase 4.2.

This module provides the data structures that drive every cleaning decision in
the GridSense AI ETL pipeline.  **No cleaning logic lives here** – this module
is purely declarative so that rules can be authored, serialised, and versioned
independently of the implementation.

Supported strategies
--------------------
Missing values: ``drop``, ``mean``, ``median``, ``mode``, ``forward_fill``,
``backward_fill``, ``interpolate``, ``constant``.

Duplicates: ``keep_first``, ``keep_last``, ``drop_all``.

Outlier detection: ``iqr``, ``zscore``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

# ---------------------------------------------------------------------------
# Allowed strategy constants
# ---------------------------------------------------------------------------

MISSING_STRATEGIES = {
    "drop",
    "mean",
    "median",
    "mode",
    "forward_fill",
    "backward_fill",
    "interpolate",
    "constant",
}

DUPLICATE_STRATEGIES = {"keep_first", "keep_last", "drop_all"}

OUTLIER_METHODS = {"iqr", "zscore"}


# ---------------------------------------------------------------------------
# Column-level rule dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MissingValueRule:
    """Rule for handling missing values in a single column.

    Attributes
    ----------
    strategy:
        One of the values in :data:`MISSING_STRATEGIES`.
    constant_value:
        Fill value used when ``strategy == "constant"``.
    """

    strategy: str = "drop"
    constant_value: Any = None


@dataclass(slots=True)
class DataTypeRule:
    """Rule defining the target data type for a column.

    Attributes
    ----------
    target_type:
        One of ``"integer"``, ``"float"``, ``"boolean"``, ``"string"``,
        ``"date"``, or ``"timestamp"``.
    """

    target_type: str


@dataclass(slots=True)
class UnitRule:
    """Rule defining the source and target unit for a numeric column.

    Attributes
    ----------
    source_unit:
        Unit the raw data is expressed in (e.g. ``"m/s"``).
    target_unit:
        Unit the cleaned data should be expressed in (e.g. ``"km/h"``).
    """

    source_unit: str
    target_unit: str


@dataclass(slots=True)
class TimestampRule:
    """Rule for parsing and UTC-normalising a timestamp column.

    Attributes
    ----------
    timezone:
        IANA timezone string of the source data (default ``"UTC"``).
    output_format:
        Currently only ``"iso8601"`` is supported.
    """

    timezone: str = "UTC"
    output_format: str = "iso8601"


# ---------------------------------------------------------------------------
# Dataset-level and top-level config dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DatasetCleaningConfig:
    """All cleaning rules that apply to a single dataset.

    Attributes
    ----------
    dataset_name:
        Unique identifier for the dataset (must match the staging directory name).
    missing_values:
        Per-column :class:`MissingValueRule` map.
    duplicates:
        Global duplicate strategy for this dataset (one of
        :data:`DUPLICATE_STRATEGIES`).
    dtypes:
        Per-column :class:`DataTypeRule` map.
    units:
        Per-column :class:`UnitRule` map.
    categoricals:
        Per-column value-mapping dictionary (``{raw_value: canonical_value}``).
    timestamps:
        Per-column :class:`TimestampRule` map.
    constant_fill_values:
        Shorthand constant fill values keyed by column name.
    outlier_columns:
        Per-column outlier method (``"iqr"`` or ``"zscore"``).
    """

    dataset_name: str
    missing_values: Dict[str, MissingValueRule] = field(default_factory=dict)
    duplicates: str = "keep_first"
    dtypes: Dict[str, DataTypeRule] = field(default_factory=dict)
    units: Dict[str, UnitRule] = field(default_factory=dict)
    categoricals: Dict[str, Dict[str, str]] = field(default_factory=dict)
    timestamps: Dict[str, TimestampRule] = field(default_factory=dict)
    constant_fill_values: Dict[str, Any] = field(default_factory=dict)
    outlier_columns: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class CleaningConfig:
    """Top-level cleaning configuration for all datasets.

    Attributes
    ----------
    datasets:
        Map of dataset name to its :class:`DatasetCleaningConfig`.
    """

    datasets: Dict[str, DatasetCleaningConfig] = field(default_factory=dict)

    @staticmethod
    def from_dict(config_map: Mapping[str, Any]) -> "CleaningConfig":
        """Build a :class:`CleaningConfig` from a nested dictionary.

        This factory enables configuration to be loaded from YAML, JSON, or
        environment-specific Python dicts without any coupling to a specific
        serialisation format.

        Parameters
        ----------
        config_map:
            Nested mapping following the schema::

                {
                    "datasets": {
                        "<dataset_name>": {
                            "missing_values": { "<column>": {"strategy": "...", ...} },
                            "duplicates": "keep_first",
                            "dtypes": { "<column>": "<type>" },
                            "units": { "<column>": {"source_unit": "...", "target_unit": "..."} },
                            "categoricals": { "<column>": { "<raw>": "<canonical>" } },
                            "timestamps": { "<column>": {"timezone": "UTC"} },
                            "constant_fill_values": { "<column>": <value> },
                            "outlier_columns": { "<column>": "iqr"|"zscore" },
                        }
                    }
                }

        Returns
        -------
        CleaningConfig
        """
        datasets: Dict[str, DatasetCleaningConfig] = {}
        for dataset_name, raw_config in config_map.get("datasets", {}).items():
            datasets[dataset_name] = DatasetCleaningConfig(
                dataset_name=dataset_name,
                missing_values={
                    column: MissingValueRule(
                        strategy=value.get("strategy", "drop"),
                        constant_value=value.get("constant_value"),
                    )
                    for column, value in raw_config.get("missing_values", {}).items()
                },
                duplicates=raw_config.get("duplicates", "keep_first"),
                dtypes={
                    column: DataTypeRule(target_type=target)
                    for column, target in raw_config.get("dtypes", {}).items()
                },
                units={
                    column: UnitRule(
                        source_unit=rule.get("source_unit", ""),
                        target_unit=rule.get("target_unit", ""),
                    )
                    for column, rule in raw_config.get("units", {}).items()
                },
                categoricals={
                    column: {
                        str(key).lower().strip(): str(mapped)
                        for key, mapped in mapping.items()
                    }
                    for column, mapping in raw_config.get("categoricals", {}).items()
                },
                timestamps={
                    column: TimestampRule(
                        timezone=rule.get("timezone", "UTC"),
                        output_format=rule.get("output_format", "iso8601"),
                    )
                    for column, rule in raw_config.get("timestamps", {}).items()
                },
                constant_fill_values=raw_config.get("constant_fill_values", {}),
                outlier_columns=raw_config.get("outlier_columns", {}),
            )

        return CleaningConfig(datasets=datasets)


def default_cleaning_config() -> CleaningConfig:
    """Return the default cleaning configuration for known GridSense datasets.

    Covers the three primary datasets ingested in Phase 3:

    - ``cea`` – Central Electricity Authority demand/supply data.
    - ``weather`` – Open-Meteo meteorological observations.
    - ``aqi`` – WAQI air-quality index readings.

    Returns
    -------
    CleaningConfig
    """
    return CleaningConfig.from_dict(
        {
            "datasets": {
                "cea": {
                    "missing_values": {
                        "demand_mw": {"strategy": "interpolate"},
                        "supply_mw": {"strategy": "interpolate"},
                    },
                    "duplicates": "keep_first",
                    "dtypes": {
                        "demand_mw": "float",
                        "supply_mw": "float",
                        "timestamp": "timestamp",
                        "state": "string",
                    },
                    "units": {
                        "demand_mw": {"source_unit": "mw", "target_unit": "mw"},
                        "supply_mw": {"source_unit": "mw", "target_unit": "mw"},
                    },
                    "categoricals": {
                        "state": {
                            "nct of delhi": "Delhi",
                            "delhi": "Delhi",
                        }
                    },
                    "timestamps": {"timestamp": {"timezone": "UTC"}},
                    "outlier_columns": {"demand_mw": "iqr", "supply_mw": "zscore"},
                },
                "weather": {
                    "missing_values": {
                        "temperature_c": {"strategy": "mean"},
                        "wind_speed": {"strategy": "median"},
                    },
                    "duplicates": "keep_last",
                    "dtypes": {
                        "temperature_c": "float",
                        "wind_speed": "float",
                        "humidity": "float",
                        "timestamp": "timestamp",
                        "latitude": "float",
                        "longitude": "float",
                    },
                    "units": {
                        "temperature_c": {
                            "source_unit": "celsius",
                            "target_unit": "celsius",
                        },
                        "wind_speed": {"source_unit": "m/s", "target_unit": "km/h"},
                        "pressure": {"source_unit": "pa", "target_unit": "hpa"},
                        "rainfall": {"source_unit": "cm", "target_unit": "mm"},
                        "humidity": {"source_unit": "ratio", "target_unit": "percent"},
                    },
                    "timestamps": {"timestamp": {"timezone": "UTC"}},
                    "outlier_columns": {
                        "temperature_c": "iqr",
                        "wind_speed": "zscore",
                    },
                },
                "aqi": {
                    "missing_values": {
                        "aqi": {"strategy": "forward_fill"},
                    },
                    "duplicates": "drop_all",
                    "dtypes": {
                        "aqi": "integer",
                        "timestamp": "timestamp",
                        "latitude": "float",
                        "longitude": "float",
                    },
                    "timestamps": {"timestamp": {"timezone": "UTC"}},
                    "outlier_columns": {"aqi": "iqr"},
                },
            }
        }
    )


def get_dataset_config(
    cleaning_config: CleaningConfig,
    dataset_name: str,
) -> Optional[DatasetCleaningConfig]:
    """Return per-dataset cleaning config if present, otherwise ``None``.

    Parameters
    ----------
    cleaning_config:
        Top-level :class:`CleaningConfig` instance.
    dataset_name:
        Dataset identifier (case-sensitive).

    Returns
    -------
    DatasetCleaningConfig | None
    """
    return cleaning_config.datasets.get(dataset_name)
