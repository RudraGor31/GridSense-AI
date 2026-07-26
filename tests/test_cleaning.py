"""Comprehensive tests for Phase 4.2 – Data Cleaning & Standardization.

Coverage
--------
- Missing value strategies: drop, mean, median, mode, forward_fill,
  backward_fill, interpolate, constant.
- Duplicate handling: keep_first, keep_last, drop_all, unknown strategy.
- Column standardization: snake_case, whitespace trim, duplicate column
  collision, invisible character removal.
- Text cleaning: Unicode normalisation, invisible characters, whitespace.
- Data type coercion: integer, float, boolean, string, timestamp.
- Timestamp standardization: UTC conversion, timezone metadata, naive datetime,
  invalid format.
- Boolean normalisation: truthy/falsy string variants.
- Categorical mapping: case-insensitive, whitespace-tolerant lookups.
- Unit conversion: m/s → km/h, Pa → hPa, cm → mm, F → C, ratio → percent,
  kW → MW, identity conversions.
- Coordinate validation: out-of-range lat/lon, invalid format.
- Outlier flagging: IQR method, Z-score method, minimum data guard, unknown
  method.
- Cleaning score: computation with retention, errors, and warnings.
- CleaningConfig.from_dict: complete round-trip parsing.
- CleaningEngine: end-to-end integration including file I/O and audit trail.
- Audit: record creation, write_audit_log, write_cleaning_summary.
- compute_cleaning_score: edge cases (zero rows, no errors, heavy penalties).
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.etl.audit import (
    AuditRecord,
    CleaningSummary,
    compute_cleaning_score,
    write_audit_log,
    write_cleaning_summary,
)
from src.etl.clean import CleaningEngine, CleaningResult
from src.etl.cleaning_rules import (
    CleaningConfig,
    MissingValueRule,
    UnitRule,
    default_cleaning_config,
    get_dataset_config,
)
from src.etl.duplicates import handle_duplicates
from src.etl.missing_values import handle_missing_values
from src.etl.normalization import flag_outliers, standardize_units, validate_coordinates
from src.etl.standardize import (
    normalize_column_name,
    normalize_text,
    standardize_columns,
    standardize_types_and_categories,
    to_bool,
    to_timestamp_utc,
)

# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------


def _make_config(overrides: Dict[str, Any] | None = None) -> CleaningConfig:
    """Return a minimal :class:`CleaningConfig` for the ``"test"`` dataset."""
    base: Dict[str, Any] = {
        "datasets": {
            "test": {
                "missing_values": {
                    "value": {"strategy": "mean"},
                    "label": {"strategy": "constant", "constant_value": "unknown"},
                },
                "duplicates": "keep_first",
                "dtypes": {
                    "value": "float",
                    "count": "integer",
                    "active": "boolean",
                    "name": "string",
                    "ts": "timestamp",
                },
                "units": {
                    "speed": {"source_unit": "m/s", "target_unit": "km/h"},
                },
                "categoricals": {
                    "status": {"yes": "active", "no": "inactive"},
                },
                "timestamps": {"ts": {"timezone": "UTC"}},
                "outlier_columns": {"value": "iqr"},
            }
        }
    }
    if overrides:
        base["datasets"]["test"].update(overrides)
    return CleaningConfig.from_dict(base)


def _make_records(n: int = 5, value_start: float = 10.0) -> List[Dict[str, Any]]:
    """Return *n* simple numeric records for outlier testing."""
    return [{"value": value_start + i} for i in range(n)]


# ===========================================================================
# 1. Missing value handling
# ===========================================================================


class TestMissingValueDrop:
    def test_drop_removes_rows_with_missing_values(self) -> None:
        records = [{"x": 1}, {"x": None}, {"x": 3}]
        rules = {"x": MissingValueRule(strategy="drop")}
        cleaned, fixed, audit, warnings = handle_missing_values(records, "ds", rules)
        assert len(cleaned) == 2
        assert fixed == 1
        assert any(a.cleaning_rule == "missing_drop" for a in audit)
        assert not warnings

    def test_drop_empty_string_sentinel(self) -> None:
        records = [{"x": ""}, {"x": "value"}]
        rules = {"x": MissingValueRule(strategy="drop")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert len(cleaned) == 1
        assert fixed == 1

    def test_drop_nan_string_sentinel(self) -> None:
        records = [{"x": "nan"}, {"x": "NaN"}, {"x": "null"}, {"x": 1}]
        rules = {"x": MissingValueRule(strategy="drop")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 3
        assert len(cleaned) == 1


class TestMissingValueMean:
    def test_mean_fills_none_with_column_mean(self) -> None:
        records = [{"x": 100.0}, {"x": None}, {"x": 200.0}]
        rules = {"x": MissingValueRule(strategy="mean")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 1
        assert cleaned[1]["x"] == 150.0

    def test_mean_no_numeric_values_produces_warning(self) -> None:
        records = [{"x": None}, {"x": None}]
        rules = {"x": MissingValueRule(strategy="mean")}
        _, _, _, warnings = handle_missing_values(records, "ds", rules)
        assert any("mean" in w for w in warnings)


class TestMissingValueMedian:
    def test_median_fills_with_middle_value(self) -> None:
        records = [{"x": 1.0}, {"x": None}, {"x": 3.0}]
        rules = {"x": MissingValueRule(strategy="median")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 1
        assert cleaned[1]["x"] == 2.0


class TestMissingValueMode:
    def test_mode_fills_with_most_frequent(self) -> None:
        records = [{"x": "a"}, {"x": "b"}, {"x": "b"}, {"x": None}]
        rules = {"x": MissingValueRule(strategy="mode")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 1
        assert cleaned[3]["x"] == "b"


class TestMissingValueForwardFill:
    def test_forward_fill_propagates_previous(self) -> None:
        records = [{"x": 5}, {"x": None}, {"x": None}]
        rules = {"x": MissingValueRule(strategy="forward_fill")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 2
        assert cleaned[1]["x"] == 5
        assert cleaned[2]["x"] == 5

    def test_forward_fill_no_previous_leaves_missing(self) -> None:
        records = [{"x": None}, {"x": 10}]
        rules = {"x": MissingValueRule(strategy="forward_fill")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 0  # no previous value available
        assert cleaned[0]["x"] is None


class TestMissingValueBackwardFill:
    def test_backward_fill_propagates_next(self) -> None:
        records = [{"x": None}, {"x": None}, {"x": 7}]
        rules = {"x": MissingValueRule(strategy="backward_fill")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 2
        assert cleaned[0]["x"] == 7
        assert cleaned[1]["x"] == 7

    def test_backward_fill_no_next_leaves_missing(self) -> None:
        records = [{"x": 1}, {"x": None}]
        rules = {"x": MissingValueRule(strategy="backward_fill")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 0
        assert cleaned[1]["x"] is None


class TestMissingValueInterpolate:
    def test_interpolate_midpoint(self) -> None:
        records = [{"x": 0.0}, {"x": None}, {"x": 10.0}]
        rules = {"x": MissingValueRule(strategy="interpolate")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 1
        assert cleaned[1]["x"] == 5.0

    def test_interpolate_no_neighbours_leaves_missing(self) -> None:
        records = [{"x": None}]
        rules = {"x": MissingValueRule(strategy="interpolate")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 0
        assert cleaned[0]["x"] is None


class TestMissingValueConstant:
    def test_constant_fills_with_configured_value(self) -> None:
        records = [{"x": None}, {"x": 5}]
        rules = {"x": MissingValueRule(strategy="constant", constant_value=42)}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 1
        assert cleaned[0]["x"] == 42

    def test_constant_string_fill(self) -> None:
        records = [{"x": ""}, {"x": "hello"}]
        rules = {"x": MissingValueRule(strategy="constant", constant_value="N/A")}
        cleaned, fixed, _, _ = handle_missing_values(records, "ds", rules)
        assert fixed == 1
        assert cleaned[0]["x"] == "N/A"


class TestMissingValueUnsupportedStrategy:
    def test_unsupported_strategy_emits_warning(self) -> None:
        records = [{"x": None}]
        rules = {"x": MissingValueRule(strategy="magic_fill")}
        _, _, _, warnings = handle_missing_values(records, "ds", rules)
        assert any("Unsupported" in w for w in warnings)


class TestMissingValueEmptyDataset:
    def test_empty_records_returns_empty(self) -> None:
        records: List[Dict[str, Any]] = []
        rules = {"x": MissingValueRule(strategy="mean")}
        cleaned, fixed, audit, warnings = handle_missing_values(records, "ds", rules)
        assert cleaned == []
        assert fixed == 0
        assert audit == []


# ===========================================================================
# 2. Duplicate handling
# ===========================================================================


class TestDuplicatesKeepFirst:
    def test_keeps_first_drops_later(self) -> None:
        row = {"a": 1, "b": 2}
        records = [row, dict(row), {"a": 3}]
        deduped, removed, audit, _ = handle_duplicates(records, "ds", "keep_first")
        assert removed == 1
        assert len(deduped) == 2
        assert any(a.cleaning_rule == "duplicates_keep_first" for a in audit)

    def test_no_duplicates_unchanged(self) -> None:
        records = [{"a": 1}, {"a": 2}, {"a": 3}]
        deduped, removed, _, _ = handle_duplicates(records, "ds", "keep_first")
        assert removed == 0
        assert len(deduped) == 3


class TestDuplicatesKeepLast:
    def test_keeps_last_drops_earlier(self) -> None:
        row = {"x": 9}
        records = [dict(row), dict(row), {"x": 10}]
        deduped, removed, audit, _ = handle_duplicates(records, "ds", "keep_last")
        assert removed == 1
        assert len(deduped) == 2
        assert any(a.cleaning_rule == "duplicates_keep_last" for a in audit)


class TestDuplicatesDropAll:
    def test_drop_all_removes_every_duplicate(self) -> None:
        row = {"z": 5}
        records = [dict(row), dict(row), {"z": 6}]
        deduped, removed, audit, _ = handle_duplicates(records, "ds", "drop_all")
        assert removed == 2
        assert len(deduped) == 1
        assert deduped[0]["z"] == 6

    def test_drop_all_all_unique(self) -> None:
        records = [{"z": 1}, {"z": 2}]
        deduped, removed, _, _ = handle_duplicates(records, "ds", "drop_all")
        assert removed == 0
        assert len(deduped) == 2


class TestDuplicatesUnknownStrategy:
    def test_unknown_strategy_emits_warning_and_returns_unchanged(self) -> None:
        records = [{"a": 1}, {"a": 1}]
        deduped, removed, _, warnings = handle_duplicates(records, "ds", "nonexistent")
        assert removed == 0
        assert len(deduped) == 2
        assert any("Unsupported" in w for w in warnings)


class TestDuplicatesEmptyDataset:
    def test_empty_records_returns_empty(self) -> None:
        deduped, removed, _, _ = handle_duplicates([], "ds", "keep_first")
        assert deduped == []
        assert removed == 0


# ===========================================================================
# 3. Column standardization
# ===========================================================================


class TestNormalizeColumnName:
    def test_strips_and_lowercases(self) -> None:
        assert normalize_column_name("  Demand MW  ") == "demand_mw"

    def test_removes_illegal_characters(self) -> None:
        assert normalize_column_name("CO2 (ppm)") == "co2_ppm"

    def test_collapses_repeated_underscores(self) -> None:
        assert normalize_column_name("a__b___c") == "a_b_c"

    def test_unicode_normalisation(self) -> None:
        # Full-width letters should normalise to ASCII
        result = normalize_column_name("ｃｏｌ")
        assert result == "col"

    def test_empty_string_returns_empty(self) -> None:
        assert normalize_column_name("") == ""


class TestNormalizeText:
    def test_trims_and_collapses_whitespace(self) -> None:
        assert normalize_text("  hello   world  ") == "hello world"

    def test_removes_zero_width_space(self) -> None:
        result = normalize_text("hello\u200bworld")
        assert "\u200b" not in result

    def test_removes_bom(self) -> None:
        result = normalize_text("\ufeffdata")
        assert "\ufeff" not in result

    def test_non_string_passthrough(self) -> None:
        assert normalize_text(42) == 42
        assert normalize_text(None) is None


class TestStandardizeColumns:
    def test_renames_to_snake_case(self) -> None:
        records = [{"Demand MW": 100}]
        std, renamed, audit = standardize_columns(records, "ds")
        assert "demand_mw" in std[0]
        assert renamed == 1
        assert any(a.cleaning_rule == "column_snake_case" for a in audit)

    def test_duplicate_column_collision_dropped(self) -> None:
        # Two columns that normalise to the same name
        records = [{"price": 10, "PRICE": 20}]
        std, _, audit = standardize_columns(records, "ds")
        assert "price" in std[0]
        assert any(a.cleaning_rule == "duplicate_column_dropped" for a in audit)

    def test_string_values_trimmed(self) -> None:
        records = [{"city": "  Berlin  "}]
        std, _, _ = standardize_columns(records, "ds")
        assert std[0]["city"] == "Berlin"

    def test_non_string_values_unchanged(self) -> None:
        records = [{"count": 42, "ratio": 0.5}]
        std, renamed, _ = standardize_columns(records, "ds")
        assert std[0]["count"] == 42
        assert std[0]["ratio"] == 0.5
        assert renamed == 0


# ===========================================================================
# 4. Data type standardization
# ===========================================================================


class TestTypeCoercion:
    def test_string_to_float(self) -> None:
        records = [{"x": "3.14"}]
        typed, corrected, _, _, _ = standardize_types_and_categories(
            records, "ds", {"x": "float"}, {}, {}
        )
        assert typed[0]["x"] == pytest.approx(3.14)
        assert corrected == 1

    def test_string_to_integer(self) -> None:
        records = [{"n": "7"}]
        typed, corrected, _, _, _ = standardize_types_and_categories(
            records, "ds", {"n": "integer"}, {}, {}
        )
        assert typed[0]["n"] == 7
        assert corrected == 1

    def test_float_to_integer_truncation(self) -> None:
        records = [{"n": 9.9}]
        typed, _, _, _, _ = standardize_types_and_categories(
            records, "ds", {"n": "integer"}, {}, {}
        )
        assert typed[0]["n"] == 9

    def test_string_type_trims(self) -> None:
        records = [{"s": "  hello  "}]
        typed, corrected, _, _, _ = standardize_types_and_categories(
            records, "ds", {"s": "string"}, {}, {}
        )
        assert typed[0]["s"] == "hello"
        assert corrected == 1

    def test_null_passthrough_for_numeric(self) -> None:
        records = [{"x": None}]
        typed, corrected, _, _, _ = standardize_types_and_categories(
            records, "ds", {"x": "float"}, {}, {}
        )
        assert typed[0]["x"] is None
        assert corrected == 0


# ===========================================================================
# 5. Boolean normalisation
# ===========================================================================


class TestToBool:
    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "y"])
    def test_truthy_variants(self, raw: str) -> None:
        assert to_bool(raw) is True

    @pytest.mark.parametrize("raw", ["0", "false", "False", "no", "n"])
    def test_falsy_variants(self, raw: str) -> None:
        assert to_bool(raw) is False

    def test_bool_passthrough(self) -> None:
        assert to_bool(True) is True
        assert to_bool(False) is False

    def test_none_returns_none(self) -> None:
        assert to_bool(None) is None

    def test_unknown_value_passthrough(self) -> None:
        assert to_bool("maybe") == "maybe"

    def test_boolean_column_type(self) -> None:
        records = [{"flag": "yes"}, {"flag": "no"}, {"flag": True}]
        typed, corrected, _, _, _ = standardize_types_and_categories(
            records, "ds", {"flag": "boolean"}, {}, {}
        )
        assert typed[0]["flag"] is True
        assert typed[1]["flag"] is False
        assert typed[2]["flag"] is True
        assert corrected == 2  # "yes"→True and "no"→False are conversions


# ===========================================================================
# 6. Timestamp standardization
# ===========================================================================


class TestTimestampUTC:
    def test_converts_offset_to_utc_z(self) -> None:
        value, tz = to_timestamp_utc("2026-07-05T10:00:00+05:30")
        assert isinstance(value, str)
        assert value.endswith("Z")
        assert tz == "UTC"

    def test_utc_timestamp_unchanged_format(self) -> None:
        value, tz = to_timestamp_utc("2026-01-01T00:00:00Z")
        assert value == "2026-01-01T00:00:00Z"
        assert tz == "UTC"

    def test_naive_datetime_assumed_utc(self) -> None:
        value, tz = to_timestamp_utc("2026-06-15T12:00:00")
        assert isinstance(value, str)
        assert value.endswith("Z")
        assert tz == "UTC"

    def test_datetime_object_input(self) -> None:
        dt = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        value, tz = to_timestamp_utc(dt)
        assert value == "2026-03-01T09:00:00Z"
        assert tz == "UTC"

    def test_invalid_string_returns_invalid_label(self) -> None:
        value, tz = to_timestamp_utc("not-a-date")
        assert tz == "INVALID"
        assert value == "not-a-date"

    def test_none_returns_none_utc(self) -> None:
        value, tz = to_timestamp_utc(None)
        assert value is None
        assert tz == "UTC"

    def test_non_string_non_datetime_returns_unknown(self) -> None:
        _, tz = to_timestamp_utc(12345)
        assert tz == "UNKNOWN"

    def test_timestamp_column_emits_timezone_metadata(self) -> None:
        records = [{"ts": "2026-07-05T10:00:00+05:30"}]
        _, _, _, tz_meta, _ = standardize_types_and_categories(
            records, "ds", {"ts": "timestamp"}, {}, {}
        )
        assert tz_meta.get("ts") == "UTC"


# ===========================================================================
# 7. Categorical mapping
# ===========================================================================


class TestCategoricalMapping:
    def test_maps_raw_value_to_canonical(self) -> None:
        records = [{"status": "yes"}, {"status": "no"}, {"status": "YES"}]
        _, _, audit, _, _ = standardize_types_and_categories(
            records,
            "ds",
            {},
            {"status": {"yes": "active", "no": "inactive"}},
            {},
        )
        assert records[0]["status"] == "active"
        assert records[1]["status"] == "inactive"
        # "YES" normalises to "yes" after lower()
        assert records[2]["status"] == "active"
        assert any(a.cleaning_rule == "categorical_mapping" for a in audit)

    def test_unmapped_value_unchanged(self) -> None:
        records = [{"status": "maybe"}]
        standardize_types_and_categories(
            records, "ds", {}, {"status": {"yes": "active"}}, {}
        )
        assert records[0]["status"] == "maybe"

    def test_none_value_skipped(self) -> None:
        records = [{"status": None}]
        standardize_types_and_categories(
            records, "ds", {}, {"status": {"yes": "active"}}, {}
        )
        assert records[0]["status"] is None


# ===========================================================================
# 8. Unit conversion
# ===========================================================================


class TestUnitConversion:
    def test_ms_to_kmh(self) -> None:
        records = [{"wind": 10.0}]
        converted, _, _ = standardize_units(
            records, "ds", {"wind": UnitRule("m/s", "km/h")}
        )
        assert converted[0]["wind"] == pytest.approx(36.0)

    def test_pa_to_hpa(self) -> None:
        records = [{"pressure": 101325.0}]
        converted, _, _ = standardize_units(
            records, "ds", {"pressure": UnitRule("pa", "hpa")}
        )
        assert converted[0]["pressure"] == pytest.approx(1013.25)

    def test_cm_to_mm(self) -> None:
        records = [{"rain": 2.5}]
        converted, _, _ = standardize_units(
            records, "ds", {"rain": UnitRule("cm", "mm")}
        )
        assert converted[0]["rain"] == pytest.approx(25.0)

    def test_fahrenheit_to_celsius(self) -> None:
        records = [{"temp": 212.0}]
        converted, _, _ = standardize_units(
            records, "ds", {"temp": UnitRule("fahrenheit", "celsius")}
        )
        assert converted[0]["temp"] == pytest.approx(100.0)

    def test_kelvin_to_celsius(self) -> None:
        records = [{"temp": 273.15}]
        converted, _, _ = standardize_units(
            records, "ds", {"temp": UnitRule("kelvin", "celsius")}
        )
        assert converted[0]["temp"] == pytest.approx(0.0)

    def test_ratio_to_percent(self) -> None:
        records = [{"humidity": 0.75}]
        converted, _, _ = standardize_units(
            records, "ds", {"humidity": UnitRule("ratio", "percent")}
        )
        assert converted[0]["humidity"] == pytest.approx(75.0)

    def test_kw_to_mw(self) -> None:
        records = [{"power": 5000.0}]
        converted, _, _ = standardize_units(
            records, "ds", {"power": UnitRule("kw", "mw")}
        )
        assert converted[0]["power"] == pytest.approx(5.0)

    def test_identity_conversion_no_audit(self) -> None:
        records = [{"power": 100.0}]
        _, audit, _ = standardize_units(records, "ds", {"power": UnitRule("mw", "mw")})
        # Identity conversion must not emit an audit record
        assert audit == []

    def test_unknown_conversion_emits_warning(self) -> None:
        records = [{"x": 1.0}]
        _, _, warnings = standardize_units(
            records, "ds", {"x": UnitRule("furlongs", "parsecs")}
        )
        assert any("No unit conversion" in w for w in warnings)

    def test_missing_column_skipped_silently(self) -> None:
        records = [{"other": 1.0}]
        converted, _, warnings = standardize_units(
            records, "ds", {"wind": UnitRule("m/s", "km/h")}
        )
        assert warnings == []

    def test_non_numeric_column_emits_warning(self) -> None:
        records = [{"wind": "fast"}]
        _, _, warnings = standardize_units(
            records, "ds", {"wind": UnitRule("m/s", "km/h")}
        )
        assert any("conversion failed" in w for w in warnings)


# ===========================================================================
# 9. Coordinate validation
# ===========================================================================


class TestCoordinateValidation:
    def test_valid_coordinates_produce_no_warnings(self) -> None:
        records = [{"latitude": 52.5, "longitude": 13.4}]
        warnings = validate_coordinates(records)
        assert warnings == []

    def test_latitude_out_of_range(self) -> None:
        records = [{"latitude": 120.0, "longitude": 13.4}]
        warnings = validate_coordinates(records)
        assert any("latitude" in w for w in warnings)

    def test_longitude_out_of_range(self) -> None:
        records = [{"latitude": 52.5, "longitude": -200.0}]
        warnings = validate_coordinates(records)
        assert any("longitude" in w for w in warnings)

    def test_invalid_coordinate_format(self) -> None:
        records = [{"latitude": "north", "longitude": "east"}]
        warnings = validate_coordinates(records)
        assert any("format" in w for w in warnings)

    def test_missing_coordinates_silently_skipped(self) -> None:
        records = [{"temperature": 20.0}]
        warnings = validate_coordinates(records)
        assert warnings == []

    def test_both_out_of_range_two_warnings(self) -> None:
        records = [{"latitude": -91.0, "longitude": 181.0}]
        warnings = validate_coordinates(records)
        assert len(warnings) == 2


# ===========================================================================
# 10. Outlier flagging
# ===========================================================================


class TestOutlierFlagging:
    def test_iqr_flags_extreme_outlier(self) -> None:
        records = [{"v": x} for x in [10, 11, 10, 12, 11, 500]]
        flagged, warnings = flag_outliers(records, {"v": "iqr"})
        assert flagged >= 1
        assert any("IQR" in w for w in warnings)

    def test_zscore_flags_extreme_value(self) -> None:
        # With 20 values at 10 and one extreme outlier at 10000, the outlier
        # achieves z ≈ 4.47 which exceeds the 3.0 threshold.
        records = [{"v": x} for x in [10] * 20 + [10000]]
        flagged, warnings = flag_outliers(records, {"v": "zscore"})
        assert flagged >= 1
        assert any("Z-score" in w for w in warnings)

    def test_no_outliers_in_uniform_data(self) -> None:
        records = [{"v": 10} for _ in range(10)]
        flagged, warnings = flag_outliers(records, {"v": "iqr"})
        assert flagged == 0
        assert warnings == []

    def test_too_few_values_skipped(self) -> None:
        records = [{"v": 1}, {"v": 1000}]  # only 2 values
        flagged, _ = flag_outliers(records, {"v": "iqr"})
        assert flagged == 0

    def test_unknown_method_emits_warning(self) -> None:
        records = _make_records(10)
        _, warnings = flag_outliers(records, {"value": "mad"})
        assert any("Unsupported" in w for w in warnings)

    def test_outliers_never_removed(self) -> None:
        """Rows must still be present after outlier flagging."""
        records = [{"v": x} for x in [10, 11, 10, 12, 11, 1000]]
        original_count = len(records)
        flag_outliers(records, {"v": "iqr"})
        assert len(records) == original_count


# ===========================================================================
# 11. Cleaning score
# ===========================================================================


class TestCleaningScore:
    def _make_summary(self, **kwargs: Any) -> CleaningSummary:
        defaults = {
            "dataset": "test",
            "rows_before": 100,
            "rows_after": 100,
        }
        defaults.update(kwargs)
        return CleaningSummary(**defaults)  # type: ignore[arg-type]

    def test_perfect_score_no_loss_no_issues(self) -> None:
        summary = self._make_summary()
        score = compute_cleaning_score(summary)
        assert score == 100.0

    def test_zero_rows_before_returns_zero(self) -> None:
        summary = self._make_summary(rows_before=0, rows_after=0)
        assert compute_cleaning_score(summary) == 0.0

    def test_full_row_loss_without_penalties(self) -> None:
        summary = self._make_summary(rows_after=0)
        assert compute_cleaning_score(summary) == 0.0

    def test_error_penalty_applied(self) -> None:
        summary = self._make_summary(errors=["e1", "e2"])
        score = compute_cleaning_score(summary)
        assert score == pytest.approx(80.0)  # 100 - 2*10

    def test_warning_penalty_applied(self) -> None:
        summary = self._make_summary(warnings=["w1"])
        score = compute_cleaning_score(summary)
        assert score == pytest.approx(97.0)  # 100 - 1*3

    def test_combined_retention_and_penalty(self) -> None:
        summary = self._make_summary(rows_after=90, errors=["e"])
        score = compute_cleaning_score(summary)
        assert score == pytest.approx(80.0)  # 90 - 10

    def test_score_clamped_to_zero_minimum(self) -> None:
        summary = self._make_summary(errors=["e"] * 20)
        score = compute_cleaning_score(summary)
        assert score == 0.0


# ===========================================================================
# 12. CleaningConfig round-trip
# ===========================================================================


class TestCleaningConfigFromDict:
    def test_all_fields_parsed(self) -> None:
        cfg = _make_config()
        ds = cfg.datasets.get("test")
        assert ds is not None
        assert "value" in ds.missing_values
        assert ds.missing_values["value"].strategy == "mean"
        assert ds.duplicates == "keep_first"
        assert ds.dtypes["count"].target_type == "integer"
        assert ds.units["speed"].source_unit == "m/s"
        assert ds.units["speed"].target_unit == "km/h"
        assert "status" in ds.categoricals
        assert ds.categoricals["status"]["yes"] == "active"
        assert ds.outlier_columns["value"] == "iqr"

    def test_default_config_has_all_datasets(self) -> None:
        cfg = default_cleaning_config()
        assert "cea" in cfg.datasets
        assert "weather" in cfg.datasets
        assert "aqi" in cfg.datasets

    def test_get_dataset_config_returns_correct(self) -> None:
        cfg = default_cleaning_config()
        ds = get_dataset_config(cfg, "weather")
        assert ds is not None
        assert ds.dataset_name == "weather"

    def test_get_dataset_config_missing_returns_none(self) -> None:
        cfg = default_cleaning_config()
        assert get_dataset_config(cfg, "nonexistent") is None


# ===========================================================================
# 13. Audit subsystem
# ===========================================================================


class TestAuditRecord:
    def test_record_has_required_fields(self) -> None:
        record = AuditRecord(
            dataset="test",
            column="value",
            original_value=None,
            new_value=42.0,
            cleaning_rule="missing_mean",
        )
        assert record.dataset == "test"
        assert record.cleaning_rule == "missing_mean"
        assert record.timestamp  # non-empty ISO string
        assert record.request_id  # non-empty

    def test_write_audit_log_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reports = Path(tmpdir)
            records = [
                AuditRecord(
                    dataset="test",
                    column="x",
                    original_value=None,
                    new_value=1,
                    cleaning_rule="missing_mean",
                )
            ]
            path = write_audit_log(records, reports, "test")
            assert path.exists()
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["cleaning_rule"] == "missing_mean"

    def test_write_cleaning_summary_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reports = Path(tmpdir)
            summary = CleaningSummary(dataset="test", rows_before=10, rows_after=8)
            path = write_cleaning_summary(summary, reports)
            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["dataset"] == "test"
            assert data["rows_before"] == 10


# ===========================================================================
# 14. CleaningEngine – end-to-end integration
# ===========================================================================


class TestCleaningEngineIntegration:
    @staticmethod
    def _write_staging(staging_dir: Path, records: List[Dict[str, Any]]) -> None:
        """Write records to a staging JSONL file."""
        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / "sample.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8"
        )

    def test_engine_produces_clean_file_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            staging_dir = root / "data" / "processed" / "staging" / "test"
            reports_dir = root / "reports"

            records = [
                {" Value ": "100", "count": "5", "ts": "2026-07-05T10:00:00+05:30"},
                {" Value ": "200", "count": "3", "ts": "2026-07-05T11:00:00+05:30"},
            ]
            self._write_staging(staging_dir, records)

            engine = CleaningEngine(
                processed_root=root / "data" / "processed",
                reports_root=reports_dir,
                cleaning_config=_make_config(
                    {
                        "missing_values": {},
                        "dtypes": {"value": "float", "count": "integer"},
                        "outlier_columns": {},
                    }
                ),
            )
            results = engine.run(dataset_filter=["test"])

            assert len(results) == 1
            result = results[0]
            assert isinstance(result, CleaningResult)
            assert result.rows_before == 2
            assert result.rows_after == 2
            assert Path(result.clean_file_path).exists()
            assert Path(result.summary_path).exists()
            assert Path(result.audit_path).exists()

    def test_engine_deduplication_reduces_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            staging_dir = root / "data" / "processed" / "staging" / "dedup_test"
            reports_dir = root / "reports"

            row = {"a": 1, "b": 2}
            records = [row, dict(row), {"a": 3, "b": 4}]
            self._write_staging(staging_dir, records)

            engine = CleaningEngine(
                processed_root=root / "data" / "processed",
                reports_root=reports_dir,
                cleaning_config=CleaningConfig.from_dict(
                    {
                        "datasets": {
                            "dedup_test": {
                                "duplicates": "keep_first",
                            }
                        }
                    }
                ),
            )
            results = engine.run()
            assert results[0].rows_after == 2

    def test_engine_no_config_applies_defaults(self) -> None:
        """Datasets without config should still run without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            staging_dir = root / "data" / "processed" / "staging" / "unknown_ds"
            reports_dir = root / "reports"

            records = [{"x": 1, "y": "hello"}]
            self._write_staging(staging_dir, records)

            engine = CleaningEngine(
                processed_root=root / "data" / "processed",
                reports_root=reports_dir,
                cleaning_config=CleaningConfig(),  # empty config
            )
            results = engine.run()
            assert len(results) == 1
            result = results[0]
            assert result.rows_before == 1
            # Warnings should mention missing config
            assert any("No cleaning config" in w for w in result.warnings)

    def test_engine_dataset_filter_skips_others(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            processed = root / "data" / "processed"
            for ds in ["alpha", "beta"]:
                staging_dir = processed / "staging" / ds
                staging_dir.mkdir(parents=True, exist_ok=True)
                (staging_dir / "data.jsonl").write_text(
                    json.dumps({"v": 1}), encoding="utf-8"
                )

            engine = CleaningEngine(
                processed_root=processed,
                reports_root=root / "reports",
                cleaning_config=CleaningConfig(),
            )
            results = engine.run(dataset_filter=["alpha"])
            assert len(results) == 1
            assert results[0].dataset_name == "alpha"

    def test_engine_full_pipeline_cea_like(self) -> None:
        """Simulate a CEA-like dataset through the full pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            staging_dir = root / "data" / "processed" / "staging" / "cea"
            reports_dir = root / "reports"

            records = [
                {
                    " Demand MW ": "1000",
                    "supply_mw": "",
                    "state": "  nct of delhi ",
                    "timestamp": "2026-07-05T10:00:00+05:30",
                },
                {
                    " Demand MW ": "1000",
                    "supply_mw": "",
                    "state": "  nct of delhi ",
                    "timestamp": "2026-07-05T10:00:00+05:30",
                },
            ]
            self._write_staging(staging_dir, records)

            cfg = CleaningConfig.from_dict(
                {
                    "datasets": {
                        "cea": {
                            "missing_values": {
                                "supply_mw": {
                                    "strategy": "constant",
                                    "constant_value": 1000,
                                },
                            },
                            "duplicates": "keep_first",
                            "dtypes": {
                                "demand_mw": "float",
                                "supply_mw": "float",
                                "timestamp": "timestamp",
                                "state": "string",
                            },
                            "categoricals": {
                                "state": {
                                    "nct of delhi": "Delhi",
                                    "delhi": "Delhi",
                                }
                            },
                            "timestamps": {"timestamp": {"timezone": "UTC"}},
                        }
                    }
                }
            )
            engine = CleaningEngine(
                processed_root=root / "data" / "processed",
                reports_root=reports_dir,
                cleaning_config=cfg,
            )
            results = engine.run(dataset_filter=["cea"])
            assert len(results) == 1
            result = results[0]
            # Duplicate removed
            assert result.rows_before == 2
            assert result.rows_after == 1
            # Clean file readable
            clean_data = json.loads(
                Path(result.clean_file_path).read_text(encoding="utf-8")
            )
            row = clean_data["rows"][0]
            assert row["demand_mw"] == pytest.approx(1000.0)
            assert row["state"] == "Delhi"
            assert row["timestamp"].endswith("Z")

    def test_empty_staging_directory_returns_no_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data" / "processed" / "staging").mkdir(parents=True)
            engine = CleaningEngine(
                processed_root=root / "data" / "processed",
                reports_root=root / "reports",
            )
            results = engine.run()
            assert results == []
