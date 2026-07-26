# ETL Data Cleaning & Standardization — Phase 4.2

> **GridSense AI** · Smart Energy Intelligence Platform  
> Phase 4.2 — Production-Grade Data Cleaning Engine

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Module Reference](#module-reference)
4. [Cleaning Pipeline Flow](#cleaning-pipeline-flow)
5. [Configuration](#configuration)
6. [Missing Value Strategies](#missing-value-strategies)
7. [Duplicate Handling](#duplicate-handling)
8. [Column Standardization](#column-standardization)
9. [Data Type Coercion](#data-type-coercion)
10. [Timestamp Standardization](#timestamp-standardization)
11. [Unit Standardization](#unit-standardization)
12. [Coordinate Validation](#coordinate-validation)
13. [Categorical Standardization](#categorical-standardization)
14. [Outlier Detection](#outlier-detection)
15. [Audit Trail](#audit-trail)
16. [Cleaning Summary & Score](#cleaning-summary--score)
17. [Inputs and Outputs](#inputs-and-outputs)
18. [Quick-Start Examples](#quick-start-examples)
19. [Best Practices](#best-practices)
20. [Testing](#testing)

---

## Overview

Phase 4.2 delivers an **enterprise-grade, configuration-driven cleaning engine** that
transforms validated staging datasets (produced in Phase 4.1) into clean, standardized
datasets ready for downstream analytics and machine learning.

Every design decision is governed by three constraints:

| Constraint | Implementation |
|---|---|
| **Auditability** | Every cell modification and row deletion emits an `AuditRecord` |
| **Reproducibility** | All behaviour is config-driven — no hardcoded dataset logic |
| **Safety** | Outliers are *flagged*, never automatically deleted |

---

## Architecture

```
data/processed/staging/<dataset>/*.jsonl
              │
              ▼
   ┌──────────────────────┐
   │   CleaningEngine     │  orchestrates the full pipeline
   └──────────┬───────────┘
              │
   ┌──────────▼───────────────────────────────────────────┐
   │  Step 1  standardize_columns()      → snake_case,    │
   │          normalize_text()             text cleanup   │
   ├──────────────────────────────────────────────────────┤
   │  Step 2  handle_missing_values()    → 8 strategies   │
   ├──────────────────────────────────────────────────────┤
   │  Step 3  handle_duplicates()        → 3 strategies   │
   ├──────────────────────────────────────────────────────┤
   │  Step 4  standardize_types_and_    → type coercion,  │
   │          categories()               categoricals     │
   ├──────────────────────────────────────────────────────┤
   │  Step 5  standardize_units()        → unit table     │
   ├──────────────────────────────────────────────────────┤
   │  Step 6  validate_coordinates()     → lat/lon check  │
   ├──────────────────────────────────────────────────────┤
   │  Step 7  flag_outliers()            → IQR / Z-score  │
   └──────────┬───────────────────────────────────────────┘
              │
   ┌──────────▼──────────────────────────────────────────┐
   │  Outputs                                            │
   │  ● data/processed/clean/<dataset>/<stem>.json       │
   │  ● reports/cleaning/<dataset>_<ts>.json             │
   │  ● reports/cleaning/audit/<dataset>/<ts>.jsonl      │
   └─────────────────────────────────────────────────────┘
```

### SOLID Compliance

| Principle | Application |
|---|---|
| **S** – Single Responsibility | Each module owns exactly one cleaning concern |
| **O** – Open/Closed | New strategies added to `UNIT_CONVERSIONS` or `CleaningConfig` without touching existing code |
| **L** – Liskov Substitution | All handler functions share compatible signatures |
| **I** – Interface Segregation | `CleaningEngine` composes small, focused functions; consumers import only what they need |
| **D** – Dependency Inversion | `CleaningEngine` depends on abstract config, not concrete dataset logic |

---

## Module Reference

| Module | Responsibility |
|---|---|
| [`src/etl/clean.py`](../src/etl/clean.py) | `CleaningEngine` orchestrator, `CleaningResult` dataclass |
| [`src/etl/cleaning_rules.py`](../src/etl/cleaning_rules.py) | Rule dataclasses, `CleaningConfig`, `default_cleaning_config()` |
| [`src/etl/missing_values.py`](../src/etl/missing_values.py) | `handle_missing_values()` — 8 configurable strategies |
| [`src/etl/duplicates.py`](../src/etl/duplicates.py) | `handle_duplicates()` — keep_first / keep_last / drop_all |
| [`src/etl/standardize.py`](../src/etl/standardize.py) | Column names, text cleanup, type coercion, categorical mapping |
| [`src/etl/normalization.py`](../src/etl/normalization.py) | Unit conversion, coordinate validation, outlier flagging |
| [`src/etl/audit.py`](../src/etl/audit.py) | `AuditRecord`, `CleaningSummary`, report writers, score computation |

---

## Cleaning Pipeline Flow

The engine executes steps in a fixed, deterministic order.  Each step is idempotent
with respect to subsequent steps — the output of step N is the input to step N+1.

```
Input JSONL rows
      │
      ▼  Step 1 – Column Standardization
         normalize_column_name() → snake_case
         normalize_text()        → trim, collapse whitespace, strip invisibles
         duplicate column names  → keep first, drop collisions (audit)
      │
      ▼  Step 2 – Missing Value Handling  (per-column strategy)
         drop / mean / median / mode / forward_fill /
         backward_fill / interpolate / constant
      │
      ▼  Step 3 – Duplicate Row Handling
         keep_first / keep_last / drop_all
      │
      ▼  Step 4 – Type Coercion + Categorical Mapping
         integer / float / boolean / string / date / timestamp
         categorical value normalization (case-insensitive)
      │
      ▼  Step 5 – Unit Standardization
         UNIT_CONVERSIONS lookup table (15 supported pairs)
      │
      ▼  Step 6 – Coordinate Validation
         latitude  ∈ [−90,  90]
         longitude ∈ [−180, 180]
      │
      ▼  Step 7 – Outlier Flagging (non-destructive)
         IQR: flag if value < Q1−1.5×IQR or > Q3+1.5×IQR
         Z-score: flag if |z| > 3.0
      │
      ▼  Outputs
         clean JSON, summary JSON, audit JSONL
```

---

## Configuration

All cleaning behaviour is driven by a `CleaningConfig` object.  No dataset-specific
logic exists in any implementation module.

### Loading from a dictionary

```python
from src.etl.cleaning_rules import CleaningConfig

config = CleaningConfig.from_dict({
    "datasets": {
        "weather": {
            "missing_values": {
                "temperature_c": {"strategy": "mean"},
                "wind_speed":    {"strategy": "median"},
            },
            "duplicates": "keep_last",
            "dtypes": {
                "temperature_c": "float",
                "wind_speed":    "float",
                "timestamp":     "timestamp",
                "latitude":      "float",
                "longitude":     "float",
            },
            "units": {
                "wind_speed": {"source_unit": "m/s",    "target_unit": "km/h"},
                "pressure":   {"source_unit": "pa",     "target_unit": "hpa"},
                "rainfall":   {"source_unit": "cm",     "target_unit": "mm"},
                "humidity":   {"source_unit": "ratio",  "target_unit": "percent"},
            },
            "categoricals": {},
            "timestamps": {
                "timestamp": {"timezone": "UTC", "output_format": "iso8601"}
            },
            "outlier_columns": {
                "temperature_c": "iqr",
                "wind_speed":    "zscore",
            },
        }
    }
})
```

### Default configuration

`default_cleaning_config()` ships pre-configured rules for the three primary
GridSense datasets:

| Dataset | Key columns | Missing strategy | Duplicate strategy |
|---|---|---|---|
| `cea` | `demand_mw`, `supply_mw`, `state`, `timestamp` | interpolate | keep_first |
| `weather` | `temperature_c`, `wind_speed`, `humidity`, `pressure` | mean / median | keep_last |
| `aqi` | `aqi`, `latitude`, `longitude`, `timestamp` | forward_fill | drop_all |

---

## Missing Value Strategies

All strategies are configured per column.  The engine processes columns in
declaration order.

| Strategy | Behaviour | Suitable for |
|---|---|---|
| `drop` | Remove any row where this column is missing | Non-recoverable fields (IDs, keys) |
| `mean` | Fill with column arithmetic mean | Symmetric numeric distributions |
| `median` | Fill with column median | Skewed numeric distributions |
| `mode` | Fill with most-frequent observed value | Categorical or low-cardinality numeric |
| `forward_fill` | Propagate last seen non-missing value forward | Time-series with slow change |
| `backward_fill` | Propagate next seen non-missing value backward | Leading gaps in time-series |
| `interpolate` | Linear midpoint between nearest non-missing neighbours | Smooth numeric time-series |
| `constant` | Fill with a fixed configured value | Flag columns, defaults |

**Missing sentinels recognised:** `None`, `""`, `"nan"`, `"NaN"`, `"null"`, `"NULL"`.

### Example

```python
from src.etl.cleaning_rules import MissingValueRule
from src.etl.missing_values import handle_missing_values

records = [
    {"demand_mw": 1000.0, "state": None},
    {"demand_mw": None,   "state": "Delhi"},
    {"demand_mw": 1200.0, "state": "Delhi"},
]

rules = {
    "demand_mw": MissingValueRule(strategy="interpolate"),
    "state":     MissingValueRule(strategy="constant", constant_value="Unknown"),
}

cleaned, fixed, audit, warnings = handle_missing_values(records, "cea", rules)
# fixed == 2, cleaned[1]["demand_mw"] == 1100.0, cleaned[0]["state"] == "Unknown"
```

---

## Duplicate Handling

Duplicate detection uses a deterministic JSON serialisation of the entire row
(all keys sorted lexicographically) as the hash key.

| Strategy | Behaviour |
|---|---|
| `keep_first` | Retain first occurrence; drop all subsequent copies |
| `keep_last` | Retain last occurrence; drop all preceding copies |
| `drop_all` | Remove every row that has any duplicate — no copies kept |

Every removed row emits an `AuditRecord` with `cleaning_rule` set to
`"duplicates_keep_first"`, `"duplicates_keep_last"`, or `"duplicates_drop_all"`.

---

## Column Standardization

Applied to every row in Step 1.

### Column name normalisation

```
" Demand MW "  →  demand_mw
"CO2 (ppm)"    →  co2_ppm
"STATE"        →  state
"a__b___c"     →  a_b_c
"ｃｏｌ"      →  col        (NFKC Unicode normalisation)
```

Algorithm:
1. NFKC Unicode normalisation
2. Strip + lower-case
3. Remove characters outside `[a-z0-9_ ]`
4. Collapse whitespace runs → `_`
5. Collapse repeated `_`
6. Strip leading/trailing `_`

### Column collision handling

If two original column names normalise to the same snake_case name, the **first**
is kept and the second is dropped.  A `"duplicate_column_dropped"` audit record is
emitted.

### Text cell cleaning (`normalize_text`)

Applied to every string-typed cell value:
- NFKC Unicode normalisation
- Remove zero-width space (`U+200B`) and BOM (`U+FEFF`)
- Collapse whitespace runs to a single space
- Strip leading/trailing whitespace

---

## Data Type Coercion

Configured per column in the `dtypes` map.

| Target type | Conversion |
|---|---|
| `integer` | `int(float(value))` — handles `"7"`, `9.9` → `9` |
| `float` | `float(value)` — handles `"3.14"`, `True` → `1.0` |
| `boolean` | truthy: `1/true/yes/y`; falsy: `0/false/no/n` |
| `string` | `str(value)` + `normalize_text()` |
| `date` | ISO-8601 UTC string (date component) |
| `timestamp` | ISO-8601 UTC string with `Z` suffix |

`None` / `""` inputs are preserved as `None` for numeric types rather than
raising an error.

---

## Timestamp Standardization

All timestamps are converted to **UTC ISO-8601** format with a `Z` suffix:

```
"2026-07-05T10:00:00+05:30"  →  "2026-07-05T04:30:00Z"
"2026-01-01T00:00:00Z"       →  "2026-01-01T00:00:00Z"
"2026-06-15T12:00:00"        →  "2026-06-15T12:00:00Z"  (naive → assumed UTC)
```

Timezone metadata is preserved in the clean dataset envelope:

```json
{
  "dataset": "cea",
  "cleaned_at": 1751800000.0,
  "timezone_metadata": { "timestamp": "UTC" },
  "rows": [ ... ]
}
```

Possible `tz_label` values:

| Label | Meaning |
|---|---|
| `UTC` | Successfully converted to UTC |
| `INVALID` | Could not parse as ISO-8601 datetime |
| `UNKNOWN` | Non-string, non-datetime input received |

---

## Unit Standardization

All conversions are defined in `UNIT_CONVERSIONS` — a static `dict` keyed by
`(source_unit, target_unit)` tuples.  No conversion logic is embedded in
dataset configurations.

### Supported conversions

| Domain | Source → Target | Factor |
|---|---|---|
| **Temperature** | Celsius → Celsius | identity |
| | Fahrenheit → Celsius | (x − 32) × 5/9 |
| | Kelvin → Celsius | x − 273.15 |
| **Wind Speed** | m/s → km/h | × 3.6 |
| | km/h → km/h | identity |
| **Rainfall** | cm → mm | × 10 |
| | mm → mm | identity |
| **Power** | W → kW | ÷ 1 000 |
| | kW → kW | identity |
| | kW → MW | ÷ 1 000 |
| | MW → MW | identity |
| **Pressure** | Pa → hPa | ÷ 100 |
| | hPa → hPa | identity |
| **Humidity** | ratio → percent | × 100 |
| | percent → percent | identity |

Identity conversions (e.g. `mw → mw`) produce **no audit record** — only
actual transformations are recorded.

---

## Coordinate Validation

`validate_coordinates()` inspects every row for `latitude` and `longitude` fields.

| Field | Valid range | Out-of-range action |
|---|---|---|
| `latitude` | [−90, 90] | Warning emitted, row retained |
| `longitude` | [−180, 180] | Warning emitted, row retained |

Rows with missing or non-numeric coordinates are silently skipped.

---

## Categorical Standardization

Categorical mapping is case-insensitive and whitespace-tolerant.

```python
categoricals = {
    "state": {
        "nct of delhi": "Delhi",
        "delhi":        "Delhi",
    },
    "energy_source": {
        "solar pv":   "Solar",
        "wind power": "Wind",
        "hydro":      "Hydro",
    },
}
```

Lookup key computation: `normalize_text(str(value)).lower()`.

Unmapped values are left unchanged.  Every remapped cell emits a
`"categorical_mapping"` audit record.

---

## Outlier Detection

Outlier detection is **non-destructive**.  Rows are never removed; outlier cells
are flagged as warnings in both the pipeline warnings list and the cleaning summary.

### IQR Method

```
Q1   = 25th percentile (nearest-rank)
Q3   = 75th percentile (nearest-rank)
IQR  = Q3 − Q1
lower_fence = Q1 − 1.5 × IQR
upper_fence = Q3 + 1.5 × IQR

Flag if: value < lower_fence  OR  value > upper_fence
```

### Z-Score Method

```
μ = mean of column values
σ = population standard deviation

Flag if: |z| > 3.0  where  z = (value − μ) / σ
```

Minimum data guard: fewer than 3 non-missing values → outlier detection skipped
(results would not be statistically meaningful).

### Configuration

```python
"outlier_columns": {
    "demand_mw":     "iqr",
    "temperature_c": "iqr",
    "wind_speed":    "zscore",
}
```

---

## Audit Trail

Every cleaning action is recorded as an `AuditRecord`:

```python
@dataclass
class AuditRecord:
    dataset:       str    # e.g. "weather"
    column:        str    # e.g. "wind_speed"  or  "<row>"
    original_value: Any   # value before change
    new_value:      Any   # value after change  (or "<ROW_DROPPED>")
    cleaning_rule:  str   # e.g. "missing_mean", "dtype_float", "unit_m/s_to_km/h"
    timestamp:      str   # UTC ISO-8601
    request_id:     str   # unique run identifier
    row_index:      int   # zero-based row index (−1 = unknown)
```

Audit records are written atomically to:

```
reports/cleaning/audit/<dataset>/<YYYYMMDDTHHMMSSz>.jsonl
```

One line per record; each line is a JSON object.  Files are never overwritten —
each pipeline run appends a new timestamped file.

### Cleaning rules reference

| Cleaning rule slug | Source |
|---|---|
| `column_snake_case` | Column rename |
| `duplicate_column_dropped` | Column collision |
| `missing_drop` | Drop strategy |
| `missing_mean` / `missing_median` / … | Fill strategies |
| `missing_forward_fill` / `missing_backward_fill` | Fill strategies |
| `missing_interpolate` | Interpolation |
| `duplicates_keep_first` / `keep_last` / `drop_all` | Duplicate removal |
| `dtype_float` / `dtype_integer` / `dtype_boolean` / … | Type coercion |
| `categorical_mapping` | Categorical remapping |
| `unit_<src>_to_<tgt>` | Unit conversion (e.g. `unit_m/s_to_km/h`) |

---

## Cleaning Summary & Score

A `CleaningSummary` is generated after every dataset cleaning run:

```json
{
  "dataset": "weather",
  "rows_before": 1440,
  "rows_after": 1432,
  "missing_values_fixed": 14,
  "duplicates_removed": 8,
  "columns_renamed": 6,
  "data_types_corrected": 1440,
  "outliers_flagged": 3,
  "execution_time_seconds": 0.042,
  "cleaning_score": 91.0,
  "warnings": ["Outlier flagged by IQR | row=723 ..."],
  "errors": [],
  "created_at": "2026-07-06T11:00:00+00:00",
  "request_id": "GRIDSENSE-abc123"
}
```

### Cleaning Score formula

```
retention_ratio = rows_after / rows_before         (clamped to [0, 1])
penalty         = (errors × 10) + (warnings × 3)
score           = (retention_ratio × 100) − penalty
score           = clamp(score, 0.0, 100.0)
```

Summaries are written to `reports/cleaning/<dataset>_<timestamp>.json`.

---

## Inputs and Outputs

```
INPUT
  data/processed/staging/<dataset>/*.jsonl
    One JSON object per line.
    Produced by Phase 4.1 ETL validation pipeline.

OUTPUT (per file)
  data/processed/clean/<dataset>/<stem>.json
    JSON envelope:
    {
      "dataset": "<name>",
      "cleaned_at": <unix_timestamp>,
      "timezone_metadata": { "<col>": "UTC" },
      "rows": [ ... ]
    }

REPORTS (per run)
  reports/cleaning/<dataset>_<timestamp>.json
    CleaningSummary JSON.

  reports/cleaning/audit/<dataset>/<timestamp>.jsonl
    One AuditRecord JSON per line.
```

---

## Quick-Start Examples

### Run the full cleaning pipeline

```python
from src.etl.clean import CleaningEngine

engine = CleaningEngine()
results = engine.run()

for r in results:
    print(f"{r.dataset_name}: {r.rows_before}→{r.rows_after} rows | score={r.cleaning_score}")
```

### Run for a specific dataset only

```python
results = engine.run(dataset_filter=["weather"])
```

### Use a custom configuration

```python
from src.etl.clean import CleaningEngine
from src.etl.cleaning_rules import CleaningConfig

config = CleaningConfig.from_dict({
    "datasets": {
        "my_dataset": {
            "missing_values": {"value": {"strategy": "median"}},
            "duplicates": "keep_first",
            "dtypes": {"value": "float", "ts": "timestamp"},
            "outlier_columns": {"value": "iqr"},
        }
    }
})

engine = CleaningEngine(cleaning_config=config)
results = engine.run(dataset_filter=["my_dataset"])
```

### Use individual cleaning functions

```python
from src.etl.missing_values import handle_missing_values
from src.etl.cleaning_rules import MissingValueRule

records = [{"x": None}, {"x": 10.0}, {"x": None}, {"x": 20.0}]
rules = {"x": MissingValueRule(strategy="interpolate")}

cleaned, fixed, audit, warnings = handle_missing_values(records, "demo", rules)
# cleaned[0]["x"] == None  (no left neighbour)
# cleaned[2]["x"] == 15.0  (midpoint of 10 and 20)
```

### Read and inspect an audit log

```python
import json
from pathlib import Path

audit_file = Path("reports/cleaning/audit/weather/20260706T110000Z.jsonl")
records = [json.loads(line) for line in audit_file.read_text().splitlines()]

for r in records:
    if r["cleaning_rule"].startswith("unit_"):
        print(f"Row {r['row_index']}: {r['column']} "
              f"{r['original_value']} → {r['new_value']}")
```

---

## Best Practices

### Adding a new unit conversion

Edit `UNIT_CONVERSIONS` in [`normalization.py`](../src/etl/normalization.py):

```python
UNIT_CONVERSIONS[("mph", "km/h")] = lambda x: x * 1.60934
```

No other code changes required.

### Adding a new dataset

Add an entry to `CleaningConfig.from_dict(...)` or to `default_cleaning_config()`.
No implementation changes required.

### Extending missing value strategies

1. Add the strategy slug to `MISSING_STRATEGIES` in `cleaning_rules.py`.
2. Add a branch to `handle_missing_values()` in `missing_values.py`.
3. Add at least one test to `tests/test_cleaning.py`.

### Keeping outlier records for review

Outlier warnings are stored in the `CleaningSummary.warnings` list and in the
`reports/cleaning/<dataset>_*.json` file.  Downstream pipelines can parse these
files to build outlier dashboards without re-running the cleaning engine.

### Reproducing a cleaning run

Every output file embeds a `request_id` and `created_at` timestamp.  To reproduce:
1. Use the same `CleaningConfig` dict (version-controlled).
2. Use the same input staging files (immutable, SHA-256 checksummed in Phase 3).
3. The audit JSONL shows every transformation applied in order.

### Performance

- Cleaning is single-threaded and pure Python — deliberately avoiding pandas/numpy
  to keep the dependency footprint minimal and the behaviour deterministic.
- For very large datasets (> 1 M rows), consider partitioning JSONL files before
  staging and running `engine.run(dataset_filter=...)` per partition.

---

## Testing

Phase 4.2 ships with **110 pytest tests** in
[`tests/test_cleaning.py`](../tests/test_cleaning.py) across 14 test classes.

```
Class                          # Tests  Coverage area
─────────────────────────────  ───────  ──────────────────────────────────────
TestMissingValueDrop               3    drop strategy, sentinels
TestMissingValueMean               2    mean fill, no-data warning
TestMissingValueMedian             1    median fill
TestMissingValueMode               1    mode fill
TestMissingValueForwardFill        2    forward fill, no-prev guard
TestMissingValueBackwardFill       2    backward fill, no-next guard
TestMissingValueInterpolate        2    interpolation, no-neighbour guard
TestMissingValueConstant           2    constant fill (numeric + string)
TestMissingValueUnsupportedStrategy 1   unknown strategy warning
TestMissingValueEmptyDataset       1    empty input guard
TestDuplicatesKeepFirst            2    keep_first, no-dup case
TestDuplicatesKeepLast             2    keep_last
TestDuplicatesDropAll              2    drop_all, all-unique case
TestDuplicatesUnknownStrategy      1    unknown strategy warning
TestDuplicatesEmptyDataset         1    empty input guard
TestNormalizeColumnName            5    snake_case, illegal chars, unicode
TestNormalizeText                  4    whitespace, invisible chars, non-str
TestStandardizeColumns             4    rename, collision, trim, non-str pass
TestTypeCoercion                   5    float, int, truncation, string, null
TestToBool                         8    truthy/falsy variants, passthrough
TestTimestampUTC                   8    offset→UTC, naive, datetime, invalid
TestCategoricalMapping             3    mapping, unmapped, None
TestUnitConversion                11    all supported pairs + edge cases
TestCoordinateValidation           6    valid, OOB, format error, skip
TestOutlierFlagging                6    IQR, Z-score, uniform, min-guard
TestCleaningScore                  7    formula edge cases
TestCleaningConfigFromDict         4    config parsing round-trip
TestAuditRecord                    3    record fields, file writes
TestCleaningEngineIntegration      6    end-to-end runs
─────────────────────────────  ───────
TOTAL                            110
```

Run the full suite:

```bash
pytest tests/test_cleaning.py -v
pytest tests/ -v   # includes Phase 1–4.1 regression tests
```

Run quality tools:

```bash
black src/etl/ tests/test_cleaning.py
ruff check src/etl/ tests/test_cleaning.py
mypy src/etl/ --ignore-missing-imports --explicit-package-bases
```
