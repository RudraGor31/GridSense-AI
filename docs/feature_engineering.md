# Feature Engineering — Phase 4.3

> **GridSense AI** · Smart Energy Intelligence Platform  
> Phase 4.3 — Production-Grade Feature Engineering Engine

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Module Reference](#module-reference)
4. [Feature Pipeline Flow](#feature-pipeline-flow)
5. [Configuration](#configuration)
6. [Feature Catalogue](#feature-catalogue)
   - [Time Features](#time-features)
   - [Weather Features](#weather-features)
   - [Energy Features](#energy-features)
   - [Air Quality Features](#air-quality-features)
   - [Rolling Features](#rolling-features)
   - [Lag Features](#lag-features)
   - [Statistical Features](#statistical-features)
   - [Interaction Features](#interaction-features)
7. [Feature Metadata](#feature-metadata)
8. [Feature Registry](#feature-registry)
9. [Feature Validation](#feature-validation)
10. [Inputs and Outputs](#inputs-and-outputs)
11. [Quick-Start Examples](#quick-start-examples)
12. [Business Logic](#business-logic)
13. [Best Practices](#best-practices)
14. [Testing](#testing)

---

## Overview

Phase 4.3 transforms **cleaned datasets** (output of Phase 4.2) into
**analytics-ready feature datasets**.  The resulting datasets power:

| Downstream Consumer | Key Features Used |
|---|---|
| KPI dashboards | Energy efficiency, AQI severity, demand flags |
| Forecasting models | Lag features, rolling windows, time cyclicals |
| Statistical analysis | Global stats, CV, cumulative sums |
| Machine-learning pipelines | All features + interaction terms |

Every feature is:
- **Configuration-driven** – no dataset-specific logic in implementation modules.
- **Documented** – carries a :class:`FeatureMetadata` descriptor (name, formula, unit, version).
- **Validated** – post-generation quality checks for missing, NaN, ±inf, out-of-range values.
- **Auditable** – a JSON report and metadata catalogue are written per run.

---

## Architecture

```
data/processed/clean/<dataset>/*.json
              │
              ▼
   ┌──────────────────────┐
   │   FeaturePipeline    │   orchestrates all 10 steps
   └──────────┬───────────┘
              │
   ┌──────────▼──────────────────────────────────────────────────┐
   │ Step 1  add_time_features()       15 temporal features       │
   ├─────────────────────────────────────────────────────────────┤
   │ Step 2  add_weather_features()     8 meteorological indices  │
   ├─────────────────────────────────────────────────────────────┤
   │ Step 3  add_energy_features()      8 demand KPI features     │
   ├─────────────────────────────────────────────────────────────┤
   │ Step 4  add_aqi_features()         6 air-quality features    │
   ├─────────────────────────────────────────────────────────────┤
   │ Step 5  add_statistical_features() 8 stats × N columns       │
   ├─────────────────────────────────────────────────────────────┤
   │ Step 6  add_rolling_features()     6 aggs × W windows × N   │
   ├─────────────────────────────────────────────────────────────┤
   │ Step 7  add_lag_features()         L lag steps × N columns   │
   ├─────────────────────────────────────────────────────────────┤
   │ Step 8  add_interaction_features() P interaction pairs       │
   ├─────────────────────────────────────────────────────────────┤
   │ Step 9  FeatureValidator           quality gate              │
   └──────────┬──────────────────────────────────────────────────┘
              │
   ┌──────────▼────────────────────────────────────────────────┐
   │ Step 10  Write outputs                                    │
   │  ● data/processed/features/<dataset>/<stem>.json          │
   │  ● reports/features/<dataset>_<ts>.json                   │
   │  ● reports/features/metadata/<dataset>_<ts>.json          │
   └───────────────────────────────────────────────────────────┘
```

### SOLID Compliance

| Principle | Application |
|---|---|
| **S** | Each module owns exactly one feature domain |
| **O** | New features added to config without touching engine code |
| **L** | All feature functions share identical signatures `(records, config) → (records, added, warnings)` |
| **I** | `FeaturePipeline` composes fine-grained, independent feature functions |
| **D** | Engine depends on abstract `FeaturePipelineConfig`, not concrete datasets |

---

## Module Reference

| Module | Responsibility |
|---|---|
| [`src/features/feature_pipeline.py`](../src/features/feature_pipeline.py) | `FeaturePipeline` orchestrator, `FeaturePipelineResult`, `FeaturePipelineConfig` |
| [`src/features/feature_metadata.py`](../src/features/feature_metadata.py) | `FeatureMetadata` dataclass, `write_metadata_report()` |
| [`src/features/feature_registry.py`](../src/features/feature_registry.py) | `FeatureRegistry` — catalogue with name/category/tag lookup |
| [`src/features/feature_validator.py`](../src/features/feature_validator.py) | `FeatureValidator`, `FeatureValidationResult` |
| [`src/features/time_features.py`](../src/features/time_features.py) | `add_time_features()`, `TimeFeaturesConfig` |
| [`src/features/weather_features.py`](../src/features/weather_features.py) | `add_weather_features()`, `WeatherFeaturesConfig` |
| [`src/features/energy_features.py`](../src/features/energy_features.py) | `add_energy_features()`, `EnergyFeaturesConfig` |
| [`src/features/air_quality_features.py`](../src/features/air_quality_features.py) | `add_aqi_features()`, `AQIFeaturesConfig` |
| [`src/features/rolling_features.py`](../src/features/rolling_features.py) | `add_rolling_features()`, `RollingFeaturesConfig`, `build_rolling_metadata()` |
| [`src/features/lag_features.py`](../src/features/lag_features.py) | `add_lag_features()`, `LagFeaturesConfig`, `build_lag_metadata()` |
| [`src/features/statistical_features.py`](../src/features/statistical_features.py) | `add_statistical_features()`, `StatisticalFeaturesConfig`, `build_statistical_metadata()` |
| [`src/features/interaction_features.py`](../src/features/interaction_features.py) | `add_interaction_features()`, `InteractionFeaturesConfig`, `build_interaction_metadata()` |

---

## Feature Pipeline Flow

Steps execute in a fixed, deterministic order. Each step's output is the
input to the next — the pipeline is fully composable.

```
Clean record dict
      │
      ▼  Step 1 – Time Features
         year, quarter, month, month_name, week, day, day_of_week,
         day_name, is_weekend, is_business_day, is_holiday,
         hour, minute, season, financial_quarter
      │
      ▼  Step 2 – Weather Features
         heat_index, wind_chill, temperature_range, feels_like,
         humidity_category, rain_category, wind_category,
         weather_severity_score
      │
      ▼  Step 3 – Energy Features
         demand_change_pct, peak_demand_flag, off_peak_flag,
         load_factor, energy_efficiency_score, demand_supply_gap,
         supply_coverage_ratio, demand_growth
      │
      ▼  Step 4 – AQI Features
         aqi_category, pollution_level, aqi_change, aqi_trend,
         aqi_severity_score, safe_exposure
      │
      ▼  Step 5 – Statistical Features  (per configured column)
         {col}_mean, {col}_median, {col}_variance, {col}_std,
         {col}_cv, {col}_pct_change, {col}_moving_avg, {col}_cumsum
      │
      ▼  Step 6 – Rolling Features  (per column × window × agg)
         {col}_rolling_{W}_{agg}
      │
      ▼  Step 7 – Lag Features  (per column × lag step)
         {col}_lag_{N}
      │
      ▼  Step 8 – Interaction Features  (per pair)
         {col_a}_x_{col_b}
      │
      ▼  Step 9 – Validation
         missing / inf / NaN / out-of-range / invalid calc checks
      │
      ▼  Step 10 – Write outputs
         feature JSON, report JSON, metadata JSON
```

---

## Configuration

All feature behaviour is driven by `FeaturePipelineConfig`.  No dataset-specific
logic lives in implementation modules.

```python
from src.features.feature_pipeline import FeaturePipeline, FeaturePipelineConfig
from src.features.rolling_features import RollingFeaturesConfig
from src.features.lag_features import LagFeaturesConfig
from src.features.statistical_features import StatisticalFeaturesConfig
from src.features.interaction_features import InteractionFeaturesConfig
from src.features.time_features import TimeFeaturesConfig

config = FeaturePipelineConfig(
    # Disable steps not relevant to this dataset
    enable_weather=False,
    enable_aqi=False,

    # Time features – add Indian public holidays
    time_config=TimeFeaturesConfig(
        holidays={"2026-01-26", "2026-08-15", "2026-10-02"}
    ),

    # Statistical features – compute stats for demand_mw
    statistical_config=StatisticalFeaturesConfig(
        columns=["demand_mw"],
        moving_avg_span=24,
    ),

    # Rolling features – 3 windows, 3 aggregations
    rolling_config=RollingFeaturesConfig(
        columns=["demand_mw", "supply_mw"],
        windows=[6, 24, 168],
        aggregations=["mean", "std", "min"],
    ),

    # Lag features – 7 lag steps
    lag_config=LagFeaturesConfig(
        columns=["demand_mw"],
        lag_steps=[1, 3, 6, 12, 24, 48, 168],
    ),

    # Interaction features – custom pairs
    interaction_config=InteractionFeaturesConfig(
        interactions=[
            ("demand_mw", "temperature_c"),
            ("demand_mw", "aqi"),
        ]
    ),
)

pipeline = FeaturePipeline(pipeline_config=config)
results = pipeline.run(dataset_filter=["cea"])
```

---

## Feature Catalogue

### Time Features

Derived from an ISO-8601 UTC timestamp column.

| Feature | Type | Description |
|---|---|---|
| `year` | int | 4-digit calendar year |
| `quarter` | int | Calendar quarter 1–4 |
| `month` | int | Month 1–12 |
| `month_name` | str | Full English month name |
| `week` | int | ISO week number 1–53 |
| `day` | int | Day of month 1–31 |
| `day_of_week` | int | 0=Monday … 6=Sunday |
| `day_name` | str | Full English day name |
| `is_weekend` | bool | True if Sat or Sun |
| `is_business_day` | bool | True if Mon–Fri |
| `is_holiday` | bool | True if date is in configured holiday set |
| `hour` | int | Hour 0–23 |
| `minute` | int | Minute 0–59 |
| `season` | str | Spring / Summer / Autumn / Winter (Northern Hemisphere) |
| `financial_quarter` | str | Q1–Q4 (April fiscal year start) |

Financial quarter mapping (April fiscal year start):

| Calendar months | Financial quarter |
|---|---|
| April – June | Q1 |
| July – September | Q2 |
| October – December | Q3 |
| January – March | Q4 |

---

### Weather Features

| Feature | Formula | Unit | Notes |
|---|---|---|---|
| `heat_index` | Rothfusz regression | °C | Applied only if T ≥ 27°C and RH ≥ 40% |
| `wind_chill` | Environment Canada formula | °C | Applied only if T ≤ 10°C and V ≥ 4.8 km/h |
| `temperature_range` | `temp_max − temp_min` | °C | Requires `temp_max` and `temp_min` |
| `feels_like` | `heat_index` if hot & humid, `wind_chill` if cold & windy, else `temperature_c` | °C | |
| `humidity_category` | Threshold-based | — | Low / Moderate / High / Very High |
| `rain_category` | Threshold-based (mm) | — | None / Light / Moderate / Heavy |
| `wind_category` | Beaufort-inspired (km/h) | — | Calm / Breeze / Moderate / Strong / Storm |
| `weather_severity_score` | `0.4×temp_dev + 0.3×wind_score + 0.3×rain_score` × 100 | 0–100 | Higher = more severe |

Humidity categories:

| RH (%) | Category |
|---|---|
| < 30 | Low |
| 30–60 | Moderate |
| 60–80 | High |
| > 80 | Very High |

---

### Energy Features

| Feature | Formula | Unit | Notes |
|---|---|---|---|
| `demand_change_pct` | `(d[t] − d[t−1]) / d[t−1] × 100` | % | First row is `None` |
| `peak_demand_flag` | `demand_mw > peak_threshold` | bool | Configurable threshold |
| `off_peak_flag` | `demand_mw < off_peak_threshold` | bool | Configurable threshold |
| `load_factor` | `mean(demand) / max(demand)` | 0–1 | Constant per file window |
| `energy_efficiency_score` | `min(supply / demand, 1) × 100` | 0–100 | 100 = fully supplied |
| `demand_supply_gap` | `demand_mw − supply_mw` | MW | Positive = deficit |
| `supply_coverage_ratio` | `min(supply / demand, 2.0)` | — | Clipped at 2.0 |
| `demand_growth` | `d[t] − d[t−1]` | MW | First row is `None` |

---

### Air Quality Features

US EPA AQI standard thresholds applied throughout.

| Feature | Type | Description |
|---|---|---|
| `aqi_category` | str | Good / Moderate / Unhealthy for Sensitive Groups / Unhealthy / Very Unhealthy / Hazardous |
| `pollution_level` | int | 1 (Good) – 6 (Hazardous) |
| `aqi_change` | float | AQI difference vs previous row |
| `aqi_trend` | str | Improving (< −5) / Stable / Worsening (> +5) |
| `aqi_severity_score` | float | `min(AQI / 500, 1) × 100` — capped at 100 |
| `safe_exposure` | bool | True if AQI < 100 (configurable) |

---

### Rolling Features

Naming convention: `{column}_rolling_{window}_{aggregation}`

Supported aggregations: `mean`, `median`, `std`, `min`, `max`, `sum`

Default window sizes: 3, 6, 12, 24, 48, 168

Examples:
- `demand_mw_rolling_24_mean` – 24-period rolling mean of demand
- `temperature_c_rolling_6_std` – 6-period rolling std of temperature

`std` requires at least 2 observations; returns `None` for single-observation windows.
`min_periods` is configurable (default: 1).

---

### Lag Features

Naming convention: `{column}_lag_{n}`

Default lag steps: 1, 3, 6, 12, 24, 48, 168

Examples:
- `demand_mw_lag_1` – demand from the previous row
- `demand_mw_lag_24` – demand 24 rows earlier (24 hours for hourly data)

Rows where `i < n` receive `fill_value` (default `None`).

---

### Statistical Features

These are computed per configured column.

| Slug | Type | Scope | Description |
|---|---|---|---|
| `{col}_mean` | float | Global | Arithmetic mean across all records |
| `{col}_median` | float | Global | Median across all records |
| `{col}_variance` | float | Global | Population variance |
| `{col}_std` | float | Global | Population standard deviation |
| `{col}_cv` | float | Global | Coefficient of variation (std / mean × 100 %) |
| `{col}_pct_change` | float | Per-row | % change vs previous row |
| `{col}_moving_avg` | float | Per-row | Simple moving average (configurable span) |
| `{col}_cumsum` | float | Per-row | Running cumulative sum |

Global statistics (mean, median, variance, std, cv) are written as **constant** values in every row — they represent the dataset-level summary.

---

### Interaction Features

Naming convention: `{col_a}_x_{col_b}`

Default interactions:

| Interaction | Business Meaning |
|---|---|
| `temperature_c_x_humidity` | Thermal-humidity stress index |
| `demand_mw_x_temperature_c` | Temperature-driven demand correlation |
| `demand_mw_x_aqi` | Pollution impact on energy consumption |
| `wind_speed_x_temperature_c` | Combined wind-temperature comfort |
| `rainfall_x_demand_mw` | Rain-driven demand patterns |

A configurable `scale` factor can normalise the product when input magnitudes differ greatly.

---

## Feature Metadata

Every generated feature is associated with a `FeatureMetadata` descriptor:

```python
@dataclass(frozen=True)
class FeatureMetadata:
    name:          str        # Unique snake_case feature name
    description:   str        # Human-readable explanation
    formula:       str        # Mathematical/algorithmic formula
    input_columns: List[str]  # Source columns required
    output_type:   str        # "float", "int", "str", "bool"
    category:      str        # "time", "weather", "energy", etc.
    dependencies:  List[str]  # Features computed before this one
    version:       str        # Semantic version (default "1.0.0")
    created_at:    str        # UTC ISO-8601 registration timestamp
    tags:          List[str]  # Free-form labels
    unit:          str        # Physical unit ("°C", "MW", "%")
```

The metadata catalogue is written to:
```
reports/features/metadata/<dataset>_<timestamp>.json
```

---

## Feature Registry

```python
from src.features.feature_registry import FeatureRegistry
from src.features.feature_metadata import FeatureMetadata

registry = FeatureRegistry()
registry.register(FeatureMetadata(name="heat_index", ...))

# Lookup
meta = registry.get("heat_index")
meta = registry.require("missing")       # raises KeyError

# Filter
time_features = registry.by_category("time")
lag_features = registry.by_tag("lag_24")
```

---

## Feature Validation

`FeatureValidator` performs non-destructive quality checks after feature generation.

| Check | When reported |
|---|---|
| Missing value | `None` or `""` in any feature column |
| Infinite value | `float("inf")` or `float("-inf")` |
| NaN value | `float("nan")` |
| Out-of-range | Value outside configured `(min, max)` bounds |
| Duplicate columns | Same column name appears twice in the record |
| Invalid calculation | Non-numeric value in a declared numeric column |

```python
from src.features.feature_validator import FeatureValidator

validator = FeatureValidator(
    numeric_columns=["demand_mw", "heat_index"],
    range_bounds={"aqi_severity_score": (0.0, 100.0)},
    allow_missing=True,     # True → warnings, False → errors
)
result = validator.validate(records, "weather", added_columns)
print(result.is_valid, result.missing_count, result.out_of_range_count)
```

---

## Inputs and Outputs

```
INPUT
  data/processed/clean/<dataset>/*.json
    Phase 4.2 clean dataset JSON envelope:
    {"dataset": "...", "cleaned_at": ..., "rows": [...]}

OUTPUT
  data/processed/features/<dataset>/<stem>.json
    Feature-enriched envelope:
    {"dataset": "...", "engineered_at": ..., "rows": [...]}

  reports/features/<dataset>_<timestamp>.json
    Feature run report (rows, feature count, warnings, validation summary)

  reports/features/metadata/<dataset>_<timestamp>.json
    Feature metadata catalogue (all FeatureMetadata descriptors)
```

---

## Quick-Start Examples

### Run the full pipeline for all datasets

```python
from src.features.feature_pipeline import FeaturePipeline

pipeline = FeaturePipeline()
results = pipeline.run()

for r in results:
    print(f"{r.dataset_name}: {r.feature_count} features, "
          f"{r.rows_processed} rows, {r.execution_time_seconds:.3f}s")
```

### Run only time + energy features

```python
from src.features.feature_pipeline import FeaturePipeline, FeaturePipelineConfig

pipeline = FeaturePipeline(
    pipeline_config=FeaturePipelineConfig(
        enable_weather=False,
        enable_aqi=False,
        enable_rolling=False,
        enable_lag=False,
        enable_statistical=False,
        enable_interaction=False,
    )
)
results = pipeline.run(dataset_filter=["cea"])
```

### Use individual feature functions

```python
from src.features.time_features import TimeFeaturesConfig, add_time_features
from src.features.rolling_features import RollingFeaturesConfig, add_rolling_features

records = [
    {"timestamp": "2026-07-05T10:00:00Z", "demand_mw": 120000.0},
    {"timestamp": "2026-07-05T11:00:00Z", "demand_mw": 130000.0},
]

# Add time features
add_time_features(records, TimeFeaturesConfig(timestamp_column="timestamp"))

# Add rolling mean (window=2)
add_rolling_features(
    records,
    RollingFeaturesConfig(columns=["demand_mw"], windows=[2], aggregations=["mean"])
)
print(records[1]["demand_mw_rolling_2_mean"])  # → 125000.0
```

### Build the feature registry

```python
from src.features.feature_pipeline import FeaturePipeline, FeaturePipelineConfig
from src.features.lag_features import LagFeaturesConfig

pipeline = FeaturePipeline(
    pipeline_config=FeaturePipelineConfig(
        lag_config=LagFeaturesConfig(columns=["demand_mw"], lag_steps=[1, 24])
    )
)
registry = pipeline.build_registry()
print(registry.names())          # ["demand_mw_lag_1", "demand_mw_lag_24"]
print(len(registry))             # 2
```

---

## Business Logic

### Heat Index (Rothfusz Regression)

The Rothfusz equation is used by NOAA and is the standard for apparent
temperature when T ≥ 27°C and RH ≥ 40%.  Outside this range the dry-bulb
temperature is returned unchanged (no misleading "feels hotter" values in
mild conditions).

### Wind Chill (Environment Canada / NOAA)

```
WC = 13.12 + 0.6215×T − 11.37×V^0.16 + 0.3965×T×V^0.16
```
Applied only when T ≤ 10°C and V ≥ 4.8 km/h.

### Load Factor

```
load_factor = mean(demand_mw) / max(demand_mw)
```
A load factor close to 1.0 indicates efficient, stable utilisation.
Close to 0 indicates highly spiky demand.

### Financial Quarter (April Fiscal Year)

Used for Indian grid (CEA) and German fiscal reporting.
April–June = Q1, July–September = Q2, October–December = Q3, January–March = Q4.

### AQI Severity Score

```
severity = min(AQI / 500.0, 1.0) × 100
```
WHOAQG max AQI of ~500 is used as the normalisation denominator.
Values above 500 AQI are capped at 100 score.

---

## Best Practices

### Adding a new feature domain

1. Create `src/features/my_features.py` with `add_my_features()` and `MyFeaturesConfig`.
2. Add a `MY_FEATURE_METADATA` list of `FeatureMetadata` descriptors.
3. Add `enable_my` and `my_config` fields to `FeaturePipelineConfig`.
4. Add a step call in `FeaturePipeline._process_file()`.
5. Write tests in `tests/test_features.py`.

### Adding a new interaction pair

```python
from src.features.interaction_features import InteractionFeaturesConfig

cfg = InteractionFeaturesConfig(
    interactions=[
        ("demand_mw", "wind_speed"),   # new pair
        *DEFAULT_INTERACTIONS,
    ]
)
```

### Controlling feature volume

For large datasets, selectively enable only required feature steps:

```python
FeaturePipelineConfig(
    enable_rolling=True,
    rolling_config=RollingFeaturesConfig(
        columns=["demand_mw"],
        windows=[24],          # fewer windows
        aggregations=["mean"], # fewer aggregations
    ),
    enable_lag=True,
    lag_config=LagFeaturesConfig(
        columns=["demand_mw"],
        lag_steps=[1, 24],     # fewer lag steps
    ),
)
```

### Version control for features

Bump `version` in `FeatureMetadata` when the formula changes.  Downstream
pipelines can read the metadata catalogue and detect version mismatches.

### Reproducibility

All feature computations are pure functions of their input records and
configuration.  To reproduce a run:
1. Use the same source clean JSON file (checksummed by Phase 3).
2. Use the same `FeaturePipelineConfig`.
3. The feature report preserves all warnings and the list of generated columns.

---

## Testing

Phase 4.3 ships **138 pytest tests** in
[`tests/test_features.py`](../tests/test_features.py) across 12 test classes.

```
Class                            # Tests  Coverage area
────────────────────────────────  ───────  ───────────────────────────────────────
TestTimeFeatures                      17   All 15 features, holidays, tz offsets
TestWeatherFeatures                   16   Heat index, wind chill, categoricals
TestEnergyFeatures                    12   Flags, load factor, efficiency, gap
TestAQIFeatures                       12   Categories, trend, severity, threshold
TestRollingFeatures                    9   All aggs, min_periods, metadata
TestLagFeatures                        8   Shifts, boundary, non-numeric
TestStatisticalFeatures                9   Global/per-row, subset, metadata
TestInteractionFeatures                6   Product, scale, metadata, sorted
TestFeatureMetadata                    6   Round-trip, frozen, write report
TestFeatureRegistry                   10   Register, lookup, duplicate handling
TestFeatureValidator                  10   All quality checks
TestFeaturePipelineIntegration         8   End-to-end file I/O, registry
────────────────────────────────  ───────
TOTAL                                138
```

Run only Phase 4.3 tests:

```bash
pytest tests/test_features.py -v
```

Run the full test suite (all phases):

```bash
pytest tests/ -v
```

Quality tools:

```bash
black src/features/ tests/test_features.py
ruff check src/features/ tests/test_features.py
mypy src/features/ --ignore-missing-imports --explicit-package-bases
```
