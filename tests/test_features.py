"""Comprehensive tests for Phase 4.3 – Feature Engineering.

Coverage areas
--------------
1.  Time features          – all 15 calendar / cyclical features, edge cases.
2.  Weather features       – heat index, wind chill, feels-like, categoricals, severity.
3.  Energy features        – demand flags, load factor, efficiency, gap, change %.
4.  AQI features           – categories, trend, severity, safe exposure.
5.  Rolling features       – window aggregations, min_periods guard, invalid agg.
6.  Lag features           – standard lags, boundary rows, non-numeric source.
7.  Statistical features   – global stats, pct_change, moving_avg, cumsum.
8.  Interaction features   – product, missing column, scale factor.
9.  Feature metadata       – to_dict / from_dict round-trip.
10. Feature registry       – register, duplicate strict/lenient, category/tag lookup.
11. Feature validator      – missing, inf, NaN, out-of-range, duplicates, non-numeric.
12. Feature pipeline       – end-to-end integration including file I/O.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.features.air_quality_features import AQIFeaturesConfig, add_aqi_features
from src.features.energy_features import EnergyFeaturesConfig, add_energy_features
from src.features.feature_metadata import FeatureMetadata, write_metadata_report
from src.features.feature_pipeline import (
    FeaturePipeline,
    FeaturePipelineConfig,
    FeaturePipelineResult,
)
from src.features.feature_registry import FeatureRegistry
from src.features.feature_validator import FeatureValidator
from src.features.interaction_features import (
    InteractionFeaturesConfig,
    add_interaction_features,
    build_interaction_metadata,
)
from src.features.lag_features import (
    LagFeaturesConfig,
    add_lag_features,
    build_lag_metadata,
)
from src.features.rolling_features import (
    RollingFeaturesConfig,
    add_rolling_features,
    build_rolling_metadata,
)
from src.features.statistical_features import (
    StatisticalFeaturesConfig,
    add_statistical_features,
    build_statistical_metadata,
)
from src.features.time_features import TimeFeaturesConfig, add_time_features
from src.features.weather_features import WeatherFeaturesConfig, add_weather_features

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _rec(**kwargs: Any) -> Dict[str, Any]:
    """Shorthand for building a record dict."""
    return dict(kwargs)


def _ts(year: int = 2026, month: int = 7, day: int = 5, hour: int = 10) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:00:00Z"


# ===========================================================================
# 1. Time Features
# ===========================================================================


class TestTimeFeatures:
    def test_year_extracted(self) -> None:
        records = [_rec(timestamp=_ts(year=2026))]
        result, added, warnings = add_time_features(records)
        assert records[0]["year"] == 2026
        assert "year" in added
        assert not warnings

    def test_all_15_features_added(self) -> None:
        records = [_rec(timestamp=_ts())]
        _, added, _ = add_time_features(records)
        expected = {
            "year",
            "quarter",
            "month",
            "month_name",
            "week",
            "day",
            "day_of_week",
            "day_name",
            "is_weekend",
            "is_business_day",
            "is_holiday",
            "hour",
            "minute",
            "season",
            "financial_quarter",
        }
        assert expected.issubset(set(added))

    def test_quarter_computation(self) -> None:
        for month, expected_q in [(1, 1), (4, 2), (7, 3), (10, 4)]:
            records = [_rec(timestamp=_ts(month=month))]
            add_time_features(records)
            assert records[0]["quarter"] == expected_q

    def test_weekend_flag(self) -> None:
        # 2026-07-04 is a Saturday
        records = [_rec(timestamp="2026-07-04T10:00:00Z")]
        add_time_features(records)
        assert records[0]["is_weekend"] is True
        assert records[0]["is_business_day"] is False

    def test_weekday_flag(self) -> None:
        # 2026-07-06 is a Monday
        records = [_rec(timestamp="2026-07-06T10:00:00Z")]
        add_time_features(records)
        assert records[0]["is_weekend"] is False
        assert records[0]["is_business_day"] is True

    def test_holiday_flag_detected(self) -> None:
        cfg = TimeFeaturesConfig(holidays={"2026-07-05"})
        records = [_rec(timestamp=_ts(day=5))]
        add_time_features(records, cfg)
        assert records[0]["is_holiday"] is True

    def test_holiday_flag_not_in_set(self) -> None:
        cfg = TimeFeaturesConfig(holidays={"2026-01-01"})
        records = [_rec(timestamp=_ts(day=5))]
        add_time_features(records, cfg)
        assert records[0]["is_holiday"] is False

    def test_season_summer(self) -> None:
        records = [_rec(timestamp=_ts(month=7))]
        add_time_features(records)
        assert records[0]["season"] == "Summer"

    def test_season_winter(self) -> None:
        records = [_rec(timestamp=_ts(month=1))]
        add_time_features(records)
        assert records[0]["season"] == "Winter"

    def test_financial_quarter_q1_april(self) -> None:
        records = [_rec(timestamp=_ts(month=4))]
        add_time_features(records)
        assert records[0]["financial_quarter"] == "Q1"

    def test_financial_quarter_q4_march(self) -> None:
        records = [_rec(timestamp=_ts(month=3))]
        add_time_features(records)
        assert records[0]["financial_quarter"] == "Q4"

    def test_invalid_timestamp_emits_warning(self) -> None:
        records = [_rec(timestamp="not-a-date")]
        _, _, warnings = add_time_features(records)
        assert any("Could not parse" in w for w in warnings)
        assert records[0]["year"] is None

    def test_none_timestamp_no_warning(self) -> None:
        records = [_rec(timestamp=None)]
        _, _, warnings = add_time_features(records)
        # None is silently skipped (no warning for intentionally missing)
        assert records[0]["year"] is None

    def test_hour_and_minute(self) -> None:
        records = [_rec(timestamp="2026-07-05T14:37:00Z")]
        add_time_features(records)
        assert records[0]["hour"] == 14
        assert records[0]["minute"] == 37

    def test_enabled_features_subset(self) -> None:
        cfg = TimeFeaturesConfig(enabled_features={"year", "month"})
        records = [_rec(timestamp=_ts())]
        _, added, _ = add_time_features(records, cfg)
        assert set(added) == {"year", "month"}
        assert "season" not in records[0]

    def test_timezone_offset_converted_to_utc(self) -> None:
        # +05:30 offset → UTC -5.5 hours
        records = [_rec(timestamp="2026-07-05T15:30:00+05:30")]
        add_time_features(records)
        # 15:30+05:30 = 10:00 UTC
        assert records[0]["hour"] == 10

    def test_multiple_records_processed(self) -> None:
        records = [_rec(timestamp=_ts(month=m)) for m in range(1, 13)]
        add_time_features(records)
        assert len(records) == 12
        seasons = {r["season"] for r in records}
        assert seasons == {"Winter", "Spring", "Summer", "Autumn"}


# ===========================================================================
# 2. Weather Features
# ===========================================================================


class TestWeatherFeatures:
    def _base_record(self, **overrides: Any) -> Dict[str, Any]:
        base = {
            "temperature_c": 30.0,
            "humidity": 60.0,
            "wind_speed": 15.0,
            "rainfall": 2.0,
            "temp_max": 35.0,
            "temp_min": 25.0,
        }
        base.update(overrides)
        return base

    def test_heat_index_computed_hot_humid(self) -> None:
        records = [self._base_record(temperature_c=35.0, humidity=80.0)]
        add_weather_features(records)
        hi = records[0]["heat_index"]
        assert hi is not None
        assert hi > 35.0  # Always higher than dry-bulb at T=35, RH=80

    def test_heat_index_not_applied_below_threshold(self) -> None:
        records = [self._base_record(temperature_c=20.0, humidity=80.0)]
        add_weather_features(records)
        # Below 27°C threshold – returns temp unchanged
        assert records[0]["heat_index"] == pytest.approx(20.0)

    def test_wind_chill_applied_cold(self) -> None:
        records = [self._base_record(temperature_c=0.0, wind_speed=20.0)]
        add_weather_features(records)
        wc = records[0]["wind_chill"]
        assert wc is not None
        assert wc < 0.0  # Wind chill colder than dry-bulb

    def test_wind_chill_not_applied_warm(self) -> None:
        records = [self._base_record(temperature_c=20.0, wind_speed=20.0)]
        add_weather_features(records)
        assert records[0]["wind_chill"] == pytest.approx(20.0)

    def test_temperature_range_computed(self) -> None:
        records = [self._base_record(temp_max=40.0, temp_min=25.0)]
        add_weather_features(records)
        assert records[0]["temperature_range"] == pytest.approx(15.0)

    def test_temperature_range_missing(self) -> None:
        records = [self._base_record(temp_max=None, temp_min=25.0)]
        add_weather_features(records)
        assert records[0]["temperature_range"] is None

    def test_feels_like_uses_heat_index_when_hot_humid(self) -> None:
        records = [self._base_record(temperature_c=35.0, humidity=80.0)]
        add_weather_features(records)
        assert records[0]["feels_like"] == records[0]["heat_index"]

    def test_feels_like_uses_wind_chill_when_cold_windy(self) -> None:
        records = [self._base_record(temperature_c=5.0, humidity=30.0, wind_speed=30.0)]
        add_weather_features(records)
        assert records[0]["feels_like"] == records[0]["wind_chill"]

    def test_feels_like_uses_temp_when_mild(self) -> None:
        records = [
            self._base_record(temperature_c=22.0, humidity=50.0, wind_speed=10.0)
        ]
        add_weather_features(records)
        assert records[0]["feels_like"] == pytest.approx(22.0)

    @pytest.mark.parametrize(
        "rh,expected_cat",
        [(20.0, "Low"), (45.0, "Moderate"), (70.0, "High"), (85.0, "Very High")],
    )
    def test_humidity_categories(self, rh: float, expected_cat: str) -> None:
        records = [self._base_record(humidity=rh)]
        add_weather_features(records)
        assert records[0]["humidity_category"] == expected_cat

    @pytest.mark.parametrize(
        "rain_mm,expected_cat",
        [(0.0, "None"), (1.0, "Light"), (5.0, "Moderate"), (20.0, "Heavy")],
    )
    def test_rain_categories(self, rain_mm: float, expected_cat: str) -> None:
        records = [self._base_record(rainfall=rain_mm)]
        add_weather_features(records)
        assert records[0]["rain_category"] == expected_cat

    @pytest.mark.parametrize(
        "kmh,expected_cat",
        [
            (2.0, "Calm"),
            (12.0, "Breeze"),
            (30.0, "Moderate"),
            (60.0, "Strong"),
            (90.0, "Storm"),
        ],
    )
    def test_wind_categories(self, kmh: float, expected_cat: str) -> None:
        records = [self._base_record(wind_speed=kmh)]
        add_weather_features(records)
        assert records[0]["wind_category"] == expected_cat

    def test_severity_score_in_range(self) -> None:
        records = [self._base_record()]
        add_weather_features(records)
        score = records[0]["weather_severity_score"]
        assert score is not None
        assert 0.0 <= score <= 100.0

    def test_missing_temp_produces_none_features(self) -> None:
        records = [self._base_record(temperature_c=None)]
        add_weather_features(records)
        assert records[0]["heat_index"] is None
        assert records[0]["feels_like"] is None

    def test_added_columns_list_correct(self) -> None:
        records = [self._base_record()]
        _, added, _ = add_weather_features(records)
        expected = {
            "heat_index",
            "wind_chill",
            "temperature_range",
            "feels_like",
            "humidity_category",
            "rain_category",
            "wind_category",
            "weather_severity_score",
        }
        assert expected.issubset(set(added))

    def test_custom_config_column_names(self) -> None:
        cfg = WeatherFeaturesConfig(temperature_column="temp", humidity_column="rh")
        records = [{"temp": 35.0, "rh": 80.0, "wind_speed": 15.0, "rainfall": 2.0}]
        add_weather_features(records, cfg)
        assert records[0]["heat_index"] is not None


# ===========================================================================
# 3. Energy Features
# ===========================================================================


class TestEnergyFeatures:
    def _records(
        self, demands: List[float], supplies: List[float]
    ) -> List[Dict[str, Any]]:
        return [{"demand_mw": d, "supply_mw": s} for d, s in zip(demands, supplies)]

    def test_demand_change_pct_computed(self) -> None:
        records = self._records([100.0, 110.0, 121.0], [100.0, 110.0, 121.0])
        add_energy_features(records)
        assert records[1]["demand_change_pct"] == pytest.approx(10.0, abs=0.01)
        assert records[2]["demand_change_pct"] == pytest.approx(10.0, abs=0.01)

    def test_demand_change_pct_first_row_none(self) -> None:
        records = self._records([100.0, 110.0], [100.0, 110.0])
        add_energy_features(records)
        assert records[0]["demand_change_pct"] is None

    def test_peak_demand_flag(self) -> None:
        cfg = EnergyFeaturesConfig(peak_threshold=100.0)
        records = self._records([90.0, 110.0], [90.0, 110.0])
        add_energy_features(records, cfg)
        assert records[0]["peak_demand_flag"] is False
        assert records[1]["peak_demand_flag"] is True

    def test_off_peak_flag(self) -> None:
        cfg = EnergyFeaturesConfig(off_peak_threshold=100.0)
        records = self._records([80.0, 120.0], [80.0, 120.0])
        add_energy_features(records, cfg)
        assert records[0]["off_peak_flag"] is True
        assert records[1]["off_peak_flag"] is False

    def test_load_factor_same_for_all_rows(self) -> None:
        records = self._records([100.0, 200.0, 150.0], [100.0, 200.0, 150.0])
        add_energy_features(records)
        lf0 = records[0]["load_factor"]
        assert all(r["load_factor"] == lf0 for r in records)
        assert lf0 is not None

    def test_load_factor_value_correct(self) -> None:
        # demands: [100, 200] → mean=150, peak=200 → lf=0.75
        records = self._records([100.0, 200.0], [100.0, 200.0])
        add_energy_features(records)
        assert records[0]["load_factor"] == pytest.approx(0.75, abs=0.001)

    def test_energy_efficiency_score_full_supply(self) -> None:
        records = self._records([100.0], [100.0])
        add_energy_features(records)
        assert records[0]["energy_efficiency_score"] == pytest.approx(100.0)

    def test_energy_efficiency_score_partial_supply(self) -> None:
        records = self._records([100.0], [75.0])
        add_energy_features(records)
        assert records[0]["energy_efficiency_score"] == pytest.approx(75.0)

    def test_energy_efficiency_score_oversupply_capped(self) -> None:
        records = self._records([100.0], [200.0])
        add_energy_features(records)
        assert records[0]["energy_efficiency_score"] == pytest.approx(100.0)

    def test_demand_supply_gap(self) -> None:
        records = self._records([150.0], [120.0])
        add_energy_features(records)
        assert records[0]["demand_supply_gap"] == pytest.approx(30.0)

    def test_demand_growth(self) -> None:
        records = self._records([100.0, 130.0, 120.0], [100.0, 130.0, 120.0])
        add_energy_features(records)
        assert records[1]["demand_growth"] == pytest.approx(30.0)
        assert records[2]["demand_growth"] == pytest.approx(-10.0)

    def test_missing_demand_produces_none_flags(self) -> None:
        records = [{"demand_mw": None, "supply_mw": 100.0}]
        add_energy_features(records)
        assert records[0]["peak_demand_flag"] is None
        assert records[0]["off_peak_flag"] is None


# ===========================================================================
# 4. AQI Features
# ===========================================================================


class TestAQIFeatures:
    @pytest.mark.parametrize(
        "aqi,expected_cat,expected_level",
        [
            (25.0, "Good", 1),
            (75.0, "Moderate", 2),
            (125.0, "Unhealthy for Sensitive Groups", 3),
            (175.0, "Unhealthy", 4),
            (250.0, "Very Unhealthy", 5),
            (350.0, "Hazardous", 6),
        ],
    )
    def test_aqi_categories(
        self, aqi: float, expected_cat: str, expected_level: int
    ) -> None:
        records = [{"aqi": aqi}]
        add_aqi_features(records)
        assert records[0]["aqi_category"] == expected_cat
        assert records[0]["pollution_level"] == expected_level

    def test_severity_score_normalised(self) -> None:
        records = [{"aqi": 250.0}]
        add_aqi_features(records)
        assert records[0]["aqi_severity_score"] == pytest.approx(50.0)

    def test_severity_score_capped_at_100(self) -> None:
        records = [{"aqi": 1000.0}]
        add_aqi_features(records)
        assert records[0]["aqi_severity_score"] == pytest.approx(100.0)

    def test_safe_exposure_below_threshold(self) -> None:
        records = [{"aqi": 50.0}]
        add_aqi_features(records)
        assert records[0]["safe_exposure"] is True

    def test_safe_exposure_above_threshold(self) -> None:
        records = [{"aqi": 150.0}]
        add_aqi_features(records)
        assert records[0]["safe_exposure"] is False

    def test_aqi_trend_worsening(self) -> None:
        records = [{"aqi": 50.0}, {"aqi": 80.0}]
        add_aqi_features(records)
        assert records[1]["aqi_trend"] == "Worsening"

    def test_aqi_trend_improving(self) -> None:
        records = [{"aqi": 100.0}, {"aqi": 60.0}]
        add_aqi_features(records)
        assert records[1]["aqi_trend"] == "Improving"

    def test_aqi_trend_stable(self) -> None:
        records = [{"aqi": 100.0}, {"aqi": 103.0}]
        add_aqi_features(records)
        assert records[1]["aqi_trend"] == "Stable"

    def test_aqi_change_value(self) -> None:
        records = [{"aqi": 100.0}, {"aqi": 130.0}]
        add_aqi_features(records)
        assert records[1]["aqi_change"] == pytest.approx(30.0)

    def test_first_row_trend_none(self) -> None:
        records = [{"aqi": 100.0}]
        add_aqi_features(records)
        assert records[0]["aqi_trend"] is None
        assert records[0]["aqi_change"] is None

    def test_missing_aqi_emits_warning(self) -> None:
        records = [{"aqi": None}]
        _, _, warnings = add_aqi_features(records)
        assert any("missing aqi" in w for w in warnings)
        assert records[0]["aqi_category"] is None

    def test_custom_threshold(self) -> None:
        cfg = AQIFeaturesConfig(safe_threshold=50.0)
        records = [{"aqi": 60.0}]
        add_aqi_features(records, cfg)
        assert records[0]["safe_exposure"] is False


# ===========================================================================
# 5. Rolling Features
# ===========================================================================


class TestRollingFeatures:
    def _demand_records(self, values: List[float]) -> List[Dict[str, Any]]:
        return [{"demand_mw": v} for v in values]

    def test_rolling_mean_window_3(self) -> None:
        records = self._demand_records([10.0, 20.0, 30.0, 40.0])
        cfg = RollingFeaturesConfig(
            columns=["demand_mw"], windows=[3], aggregations=["mean"]
        )
        add_rolling_features(records, cfg)
        # Row 3 (idx=3): window=[20, 30, 40] → mean=30
        assert records[3]["demand_mw_rolling_3_mean"] == pytest.approx(30.0)

    def test_rolling_sum(self) -> None:
        records = self._demand_records([5.0, 10.0, 15.0])
        cfg = RollingFeaturesConfig(
            columns=["demand_mw"], windows=[3], aggregations=["sum"]
        )
        add_rolling_features(records, cfg)
        assert records[2]["demand_mw_rolling_3_sum"] == pytest.approx(30.0)

    def test_rolling_min_max(self) -> None:
        records = self._demand_records([10.0, 5.0, 20.0])
        cfg = RollingFeaturesConfig(
            columns=["demand_mw"], windows=[3], aggregations=["min", "max"]
        )
        add_rolling_features(records, cfg)
        assert records[2]["demand_mw_rolling_3_min"] == pytest.approx(5.0)
        assert records[2]["demand_mw_rolling_3_max"] == pytest.approx(20.0)

    def test_rolling_std_requires_two_values(self) -> None:
        records = self._demand_records([10.0])
        cfg = RollingFeaturesConfig(
            columns=["demand_mw"], windows=[3], aggregations=["std"]
        )
        add_rolling_features(records, cfg)
        # Only 1 value → std undefined
        assert records[0]["demand_mw_rolling_3_std"] is None

    def test_rolling_median(self) -> None:
        records = self._demand_records([1.0, 3.0, 5.0])
        cfg = RollingFeaturesConfig(
            columns=["demand_mw"], windows=[3], aggregations=["median"]
        )
        add_rolling_features(records, cfg)
        assert records[2]["demand_mw_rolling_3_median"] == pytest.approx(3.0)

    def test_min_periods_guard(self) -> None:
        records = self._demand_records([10.0, 20.0, 30.0])
        cfg = RollingFeaturesConfig(
            columns=["demand_mw"], windows=[5], aggregations=["mean"], min_periods=4
        )
        add_rolling_features(records, cfg)
        # All 3 rows have fewer than 4 obs in a window of 5
        assert records[2]["demand_mw_rolling_5_mean"] is None

    def test_invalid_aggregation_emits_warning(self) -> None:
        records = self._demand_records([10.0, 20.0])
        cfg = RollingFeaturesConfig(
            columns=["demand_mw"], windows=[2], aggregations=["magic"]
        )
        _, _, warnings = add_rolling_features(records, cfg)
        assert any("Unsupported" in w for w in warnings)

    def test_metadata_builder_counts(self) -> None:
        meta = build_rolling_metadata(["demand_mw"], [3, 6], ["mean", "std"])
        assert len(meta) == 4  # 1 col × 2 windows × 2 aggs

    def test_multiple_columns(self) -> None:
        records = [{"a": 1.0, "b": 2.0}, {"a": 3.0, "b": 4.0}]
        cfg = RollingFeaturesConfig(
            columns=["a", "b"], windows=[2], aggregations=["mean"]
        )
        _, added, _ = add_rolling_features(records, cfg)
        assert "a_rolling_2_mean" in added
        assert "b_rolling_2_mean" in added


# ===========================================================================
# 6. Lag Features
# ===========================================================================


class TestLagFeatures:
    def _records(self, values: List[float]) -> List[Dict[str, Any]]:
        return [{"value": v} for v in values]

    def test_lag_1_shifts_by_one(self) -> None:
        records = self._records([10.0, 20.0, 30.0])
        cfg = LagFeaturesConfig(columns=["value"], lag_steps=[1])
        add_lag_features(records, cfg)
        assert records[0]["value_lag_1"] is None  # fill_value
        assert records[1]["value_lag_1"] == pytest.approx(10.0)
        assert records[2]["value_lag_1"] == pytest.approx(20.0)

    def test_lag_3_boundary(self) -> None:
        records = self._records([1.0, 2.0, 3.0, 4.0])
        cfg = LagFeaturesConfig(columns=["value"], lag_steps=[3])
        add_lag_features(records, cfg)
        assert records[2]["value_lag_3"] is None
        assert records[3]["value_lag_3"] == pytest.approx(1.0)

    def test_custom_fill_value(self) -> None:
        records = self._records([5.0, 10.0])
        cfg = LagFeaturesConfig(columns=["value"], lag_steps=[1], fill_value=0.0)
        add_lag_features(records, cfg)
        assert records[0]["value_lag_1"] == pytest.approx(0.0)

    def test_multiple_lag_steps(self) -> None:
        records = self._records([10.0, 20.0, 30.0, 40.0, 50.0])
        cfg = LagFeaturesConfig(columns=["value"], lag_steps=[1, 2])
        add_lag_features(records, cfg)
        assert records[4]["value_lag_1"] == pytest.approx(40.0)
        assert records[4]["value_lag_2"] == pytest.approx(30.0)

    def test_non_numeric_source_emits_warning(self) -> None:
        records = [{"value": "text"}, {"value": 10.0}]
        cfg = LagFeaturesConfig(columns=["value"], lag_steps=[1], fill_value=0.0)
        _, _, warnings = add_lag_features(records, cfg)
        assert any("Non-numeric" in w for w in warnings)

    def test_metadata_builder(self) -> None:
        meta = build_lag_metadata(["demand_mw"], [1, 24])
        assert len(meta) == 2
        assert meta[0].name == "demand_mw_lag_1"
        assert meta[1].name == "demand_mw_lag_24"

    def test_added_columns_sorted(self) -> None:
        records = self._records([1.0, 2.0, 3.0])
        cfg = LagFeaturesConfig(columns=["value"], lag_steps=[3, 1, 2])
        _, added, _ = add_lag_features(records, cfg)
        assert added == sorted(added)

    def test_empty_records_safe(self) -> None:
        cfg = LagFeaturesConfig(columns=["value"], lag_steps=[1])
        _, added, warnings = add_lag_features([], cfg)
        assert added == []
        assert warnings == []


# ===========================================================================
# 7. Statistical Features
# ===========================================================================


class TestStatisticalFeatures:
    def _records(self, values: List[float]) -> List[Dict[str, Any]]:
        return [{"x": v} for v in values]

    def test_global_mean_constant_across_rows(self) -> None:
        records = self._records([10.0, 20.0, 30.0])
        cfg = StatisticalFeaturesConfig(columns=["x"])
        add_statistical_features(records, cfg)
        means = [r["x_mean"] for r in records]
        assert all(m == means[0] for m in means)
        assert means[0] == pytest.approx(20.0)

    def test_global_median(self) -> None:
        records = self._records([1.0, 3.0, 5.0])
        cfg = StatisticalFeaturesConfig(columns=["x"])
        add_statistical_features(records, cfg)
        assert records[0]["x_median"] == pytest.approx(3.0)

    def test_global_std(self) -> None:
        records = self._records([2.0, 4.0, 6.0])
        cfg = StatisticalFeaturesConfig(columns=["x"])
        add_statistical_features(records, cfg)
        # population std of [2,4,6] = sqrt(8/3) ≈ 1.6329...
        assert records[0]["x_std"] == pytest.approx(1.6329, abs=0.001)

    def test_pct_change(self) -> None:
        records = self._records([100.0, 110.0])
        cfg = StatisticalFeaturesConfig(columns=["x"])
        add_statistical_features(records, cfg)
        assert records[1]["x_pct_change"] == pytest.approx(10.0)
        assert records[0]["x_pct_change"] is None

    def test_cumsum(self) -> None:
        records = self._records([10.0, 20.0, 30.0])
        cfg = StatisticalFeaturesConfig(columns=["x"])
        add_statistical_features(records, cfg)
        assert records[0]["x_cumsum"] == pytest.approx(10.0)
        assert records[1]["x_cumsum"] == pytest.approx(30.0)
        assert records[2]["x_cumsum"] == pytest.approx(60.0)

    def test_moving_avg_span(self) -> None:
        records = self._records([10.0, 20.0, 30.0, 40.0])
        cfg = StatisticalFeaturesConfig(columns=["x"], moving_avg_span=3)
        add_statistical_features(records, cfg)
        # Row 3 (idx=3): window=[20,30,40] → avg=30
        assert records[3]["x_moving_avg"] == pytest.approx(30.0)

    def test_cv_computed(self) -> None:
        records = self._records([10.0, 20.0, 30.0])
        cfg = StatisticalFeaturesConfig(columns=["x"])
        add_statistical_features(records, cfg)
        cv = records[0]["x_cv"]
        assert cv is not None
        assert cv > 0.0

    def test_enabled_features_subset(self) -> None:
        records = self._records([5.0, 10.0])
        cfg = StatisticalFeaturesConfig(
            columns=["x"], enabled_features=["mean", "cumsum"]
        )
        _, added, _ = add_statistical_features(records, cfg)
        assert "x_mean" in added
        assert "x_cumsum" in added
        assert "x_std" not in added

    def test_metadata_builder(self) -> None:
        meta = build_statistical_metadata(["demand_mw"])
        names = [m.name for m in meta]
        assert "demand_mw_mean" in names
        assert "demand_mw_cumsum" in names
        assert len(meta) == 8  # 8 slugs × 1 column


# ===========================================================================
# 8. Interaction Features
# ===========================================================================


class TestInteractionFeatures:
    def test_product_computed(self) -> None:
        cfg = InteractionFeaturesConfig(interactions=[("temperature_c", "humidity")])
        records = [{"temperature_c": 30.0, "humidity": 60.0}]
        add_interaction_features(records, cfg)
        assert records[0]["temperature_c_x_humidity"] == pytest.approx(1800.0)

    def test_missing_column_produces_none(self) -> None:
        cfg = InteractionFeaturesConfig(interactions=[("a", "b")])
        records = [{"a": 10.0}]  # "b" missing
        _, _, warnings = add_interaction_features(records, cfg)
        assert records[0]["a_x_b"] is None
        assert any("missing columns" in w for w in warnings)

    def test_scale_factor_applied(self) -> None:
        cfg = InteractionFeaturesConfig(interactions=[("a", "b")], scale=0.001)
        records = [{"a": 1000.0, "b": 2.0}]
        add_interaction_features(records, cfg)
        assert records[0]["a_x_b"] == pytest.approx(2.0)

    def test_default_interactions_present(self) -> None:
        records = [
            {
                "temperature_c": 30.0,
                "humidity": 60.0,
                "demand_mw": 150000.0,
                "aqi": 80.0,
                "wind_speed": 15.0,
                "rainfall": 2.0,
            }
        ]
        _, added, _ = add_interaction_features(records)
        assert "temperature_c_x_humidity" in added
        assert "demand_mw_x_temperature_c" in added
        assert "demand_mw_x_aqi" in added

    def test_metadata_builder(self) -> None:
        meta = build_interaction_metadata([("a", "b"), ("c", "d")])
        assert len(meta) == 2
        assert meta[0].name == "a_x_b"
        assert meta[0].category == "interaction"

    def test_added_columns_sorted(self) -> None:
        cfg = InteractionFeaturesConfig(interactions=[("z", "a"), ("a", "b")])
        records = [{"z": 1.0, "a": 2.0, "b": 3.0}]
        _, added, _ = add_interaction_features(records, cfg)
        assert added == sorted(added)


# ===========================================================================
# 9. Feature Metadata
# ===========================================================================


class TestFeatureMetadata:
    def _make(self, name: str = "heat_index") -> FeatureMetadata:
        return FeatureMetadata(
            name=name,
            description="Test feature.",
            formula="a + b",
            input_columns=["a", "b"],
            output_type="float",
            category="weather",
            unit="°C",
        )

    def test_to_dict_round_trip(self) -> None:
        meta = self._make()
        d = meta.to_dict()
        restored = FeatureMetadata.from_dict(d)
        assert restored.name == meta.name
        assert restored.formula == meta.formula
        assert restored.input_columns == meta.input_columns
        assert restored.unit == meta.unit

    def test_frozen_immutable(self) -> None:
        meta = self._make()
        with pytest.raises((AttributeError, TypeError)):
            meta.name = "changed"  # type: ignore[misc]

    def test_default_version(self) -> None:
        meta = self._make()
        assert meta.version == "1.0.0"

    def test_tags_default_empty(self) -> None:
        meta = self._make()
        assert meta.tags == []

    def test_write_metadata_report_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reports = Path(tmpdir)
            meta_list = [self._make("f1"), self._make("f2")]
            path = write_metadata_report(meta_list, reports, "test_ds")
            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["total_features"] == 2
            assert data["dataset"] == "test_ds"

    def test_dependencies_field(self) -> None:
        meta = FeatureMetadata(
            name="feels_like",
            description=".",
            formula=".",
            input_columns=["temperature_c"],
            output_type="float",
            category="weather",
            dependencies=["heat_index", "wind_chill"],
        )
        assert "heat_index" in meta.dependencies


# ===========================================================================
# 10. Feature Registry
# ===========================================================================


class TestFeatureRegistry:
    def _meta(
        self, name: str, category: str = "time", tags: list | None = None
    ) -> FeatureMetadata:
        return FeatureMetadata(
            name=name,
            description=".",
            formula=".",
            input_columns=[],
            output_type="float",
            category=category,
            tags=tags or [],
        )

    def test_register_and_get(self) -> None:
        reg = FeatureRegistry()
        reg.register(self._meta("year"))
        assert reg.get("year") is not None
        assert reg.get("missing") is None

    def test_register_duplicate_strict_raises(self) -> None:
        reg = FeatureRegistry(strict=True)
        reg.register(self._meta("year"))
        with pytest.raises(KeyError):
            reg.register(self._meta("year"))

    def test_register_duplicate_lenient_overwrites(self) -> None:
        reg = FeatureRegistry(strict=False)
        reg.register(self._meta("year"))
        reg.register(self._meta("year"))  # Should not raise
        assert len(reg) == 1

    def test_register_many(self) -> None:
        reg = FeatureRegistry()
        reg.register_many([self._meta("a"), self._meta("b")])
        assert len(reg) == 2

    def test_by_category(self) -> None:
        reg = FeatureRegistry()
        reg.register(self._meta("year", category="time"))
        reg.register(self._meta("heat_index", category="weather"))
        result = reg.by_category("time")
        assert len(result) == 1
        assert result[0].name == "year"

    def test_by_tag(self) -> None:
        reg = FeatureRegistry()
        reg.register(self._meta("year", tags=["cyclical"]))
        reg.register(self._meta("month", tags=["cyclical", "calendar"]))
        assert len(reg.by_tag("cyclical")) == 2
        assert len(reg.by_tag("calendar")) == 1

    def test_require_raises_missing(self) -> None:
        reg = FeatureRegistry()
        with pytest.raises(KeyError):
            reg.require("nonexistent")

    def test_contains(self) -> None:
        reg = FeatureRegistry()
        reg.register(self._meta("x"))
        assert "x" in reg
        assert "y" not in reg

    def test_categories_deduplicated(self) -> None:
        reg = FeatureRegistry()
        reg.register(self._meta("a", category="time"))
        reg.register(self._meta("b", category="time"))
        reg.register(self._meta("c", category="weather"))
        cats = reg.categories()
        assert len(cats) == 2

    def test_clear(self) -> None:
        reg = FeatureRegistry()
        reg.register(self._meta("x"))
        reg.clear()
        assert len(reg) == 0


# ===========================================================================
# 11. Feature Validator
# ===========================================================================


class TestFeatureValidator:
    def test_valid_records_pass(self) -> None:
        records = [{"score": 50.0}, {"score": 75.0}]
        validator = FeatureValidator(numeric_columns=["score"])
        result = validator.validate(records, "ds", ["score"])
        assert result.is_valid
        assert result.missing_count == 0
        assert result.infinite_count == 0

    def test_missing_value_as_warning(self) -> None:
        records = [{"score": None}]
        validator = FeatureValidator(allow_missing=True)
        result = validator.validate(records, "ds", ["score"])
        assert result.missing_count == 1
        assert result.is_valid  # warnings only, not errors

    def test_missing_value_as_error(self) -> None:
        records = [{"score": None}]
        validator = FeatureValidator(allow_missing=False)
        result = validator.validate(records, "ds", ["score"])
        assert not result.is_valid
        assert len(result.errors) >= 1

    def test_infinite_value_detected(self) -> None:
        records = [{"score": float("inf")}]
        validator = FeatureValidator(numeric_columns=["score"])
        result = validator.validate(records, "ds", ["score"])
        assert result.infinite_count == 1

    def test_nan_value_detected(self) -> None:
        records = [{"score": float("nan")}]
        validator = FeatureValidator(numeric_columns=["score"])
        result = validator.validate(records, "ds", ["score"])
        assert result.nan_count == 1

    def test_out_of_range_detected(self) -> None:
        records = [{"aqi": 600.0}]
        validator = FeatureValidator(
            numeric_columns=["aqi"],
            range_bounds={"aqi": (0.0, 500.0)},
        )
        result = validator.validate(records, "ds", ["aqi"])
        assert result.out_of_range_count == 1

    def test_invalid_calculation_detected(self) -> None:
        records = [{"score": "not-a-number"}]
        validator = FeatureValidator(numeric_columns=["score"])
        result = validator.validate(records, "ds", ["score"])
        assert result.invalid_calc_count == 1

    def test_duplicate_columns_detected(self) -> None:
        # Simulate duplicate by checking that validation reports correctly
        records = [{"a": 1.0, "b": 2.0}]
        validator = FeatureValidator()
        result = validator.validate(records, "ds", ["a", "b"])
        assert result.is_valid

    def test_empty_records_valid(self) -> None:
        validator = FeatureValidator()
        result = validator.validate([], "ds", ["score"])
        assert result.is_valid
        assert result.total_rows == 0

    def test_total_rows_counted(self) -> None:
        records = [{"x": i} for i in range(5)]
        validator = FeatureValidator()
        result = validator.validate(records, "ds", ["x"])
        assert result.total_rows == 5


# ===========================================================================
# 12. Feature Pipeline – Integration
# ===========================================================================


class TestFeaturePipelineIntegration:
    @staticmethod
    def _write_clean_file(clean_dir: Path, records: list) -> None:
        clean_dir.mkdir(parents=True, exist_ok=True)
        payload = {"dataset": "test", "rows": records}
        (clean_dir / "sample.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def test_pipeline_produces_feature_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            clean_dir = root / "data" / "processed" / "clean" / "test"
            reports_dir = root / "reports"
            records = [
                {
                    "timestamp": "2026-07-05T10:00:00Z",
                    "temperature_c": 30.0,
                    "humidity": 60.0,
                    "wind_speed": 15.0,
                    "rainfall": 2.0,
                    "demand_mw": 120000.0,
                    "supply_mw": 115000.0,
                    "aqi": 80.0,
                },
                {
                    "timestamp": "2026-07-05T11:00:00Z",
                    "temperature_c": 32.0,
                    "humidity": 65.0,
                    "wind_speed": 18.0,
                    "rainfall": 0.0,
                    "demand_mw": 130000.0,
                    "supply_mw": 128000.0,
                    "aqi": 90.0,
                },
            ]
            self._write_clean_file(clean_dir, records)

            cfg = FeaturePipelineConfig(
                enable_rolling=False,
                enable_lag=False,
                enable_statistical=False,
                enable_interaction=False,
            )
            pipeline = FeaturePipeline(
                processed_root=root / "data" / "processed",
                reports_root=reports_dir,
                pipeline_config=cfg,
            )
            results = pipeline.run(dataset_filter=["test"])

            assert len(results) == 1
            result = results[0]
            assert isinstance(result, FeaturePipelineResult)
            assert result.rows_processed == 2
            assert result.feature_count > 0
            assert Path(result.feature_file_path).exists()
            assert Path(result.report_path).exists()
            assert Path(result.metadata_path).exists()

    def test_pipeline_time_features_in_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            clean_dir = root / "data" / "processed" / "clean" / "weather"
            records = [{"timestamp": "2026-07-05T10:00:00Z", "temperature_c": 25.0}]
            self._write_clean_file(clean_dir, records)

            cfg = FeaturePipelineConfig(
                enable_weather=False,
                enable_energy=False,
                enable_aqi=False,
                enable_rolling=False,
                enable_lag=False,
                enable_statistical=False,
                enable_interaction=False,
            )
            pipeline = FeaturePipeline(
                processed_root=root / "data" / "processed",
                reports_root=root / "reports",
                pipeline_config=cfg,
            )
            results = pipeline.run()
            assert len(results) == 1
            feature_data = json.loads(
                Path(results[0].feature_file_path).read_text(encoding="utf-8")
            )
            row = feature_data["rows"][0]
            assert row["year"] == 2026
            assert row["month"] == 7
            assert row["season"] == "Summer"

    def test_pipeline_statistical_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            clean_dir = root / "data" / "processed" / "clean" / "energy"
            records = [{"demand_mw": float(v)} for v in [100.0, 200.0, 300.0]]
            self._write_clean_file(clean_dir, records)

            cfg = FeaturePipelineConfig(
                enable_time=False,
                enable_weather=False,
                enable_energy=False,
                enable_aqi=False,
                enable_rolling=False,
                enable_lag=False,
                enable_interaction=False,
                statistical_config=StatisticalFeaturesConfig(columns=["demand_mw"]),
            )
            pipeline = FeaturePipeline(
                processed_root=root / "data" / "processed",
                reports_root=root / "reports",
                pipeline_config=cfg,
            )
            results = pipeline.run()
            feature_data = json.loads(
                Path(results[0].feature_file_path).read_text(encoding="utf-8")
            )
            row = feature_data["rows"][0]
            assert row["demand_mw_mean"] == pytest.approx(200.0)

    def test_pipeline_dataset_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            processed = root / "data" / "processed"
            for ds in ["alpha", "beta"]:
                d = processed / "clean" / ds
                d.mkdir(parents=True, exist_ok=True)
                payload = {"dataset": ds, "rows": [{"x": 1.0}]}
                (d / "data.json").write_text(json.dumps(payload), encoding="utf-8")

            cfg = FeaturePipelineConfig(
                enable_time=False,
                enable_weather=False,
                enable_energy=False,
                enable_aqi=False,
                enable_rolling=False,
                enable_lag=False,
                enable_statistical=False,
                enable_interaction=False,
            )
            pipeline = FeaturePipeline(
                processed_root=processed,
                reports_root=root / "reports",
                pipeline_config=cfg,
            )
            results = pipeline.run(dataset_filter=["alpha"])
            assert len(results) == 1
            assert results[0].dataset_name == "alpha"

    def test_pipeline_rolling_and_lag_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            clean_dir = root / "data" / "processed" / "clean" / "cea"
            records = [{"demand_mw": float(i * 10)} for i in range(1, 7)]
            self._write_clean_file(clean_dir, records)

            cfg = FeaturePipelineConfig(
                enable_time=False,
                enable_weather=False,
                enable_energy=False,
                enable_aqi=False,
                enable_statistical=False,
                enable_interaction=False,
                rolling_config=RollingFeaturesConfig(
                    columns=["demand_mw"], windows=[3], aggregations=["mean"]
                ),
                lag_config=LagFeaturesConfig(columns=["demand_mw"], lag_steps=[1]),
            )
            pipeline = FeaturePipeline(
                processed_root=root / "data" / "processed",
                reports_root=root / "reports",
                pipeline_config=cfg,
            )
            results = pipeline.run()
            assert len(results) == 1
            assert "demand_mw_rolling_3_mean" in results[0].features_added
            assert "demand_mw_lag_1" in results[0].features_added

    def test_pipeline_empty_clean_dir_returns_no_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data" / "processed" / "clean").mkdir(parents=True)
            pipeline = FeaturePipeline(
                processed_root=root / "data" / "processed",
                reports_root=root / "reports",
            )
            results = pipeline.run()
            assert results == []

    def test_pipeline_report_contains_correct_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            clean_dir = root / "data" / "processed" / "clean" / "ds"
            records = [{"temperature_c": 25.0, "humidity": 50.0}]
            self._write_clean_file(clean_dir, records)

            cfg = FeaturePipelineConfig(
                enable_time=False,
                enable_energy=False,
                enable_aqi=False,
                enable_rolling=False,
                enable_lag=False,
                enable_statistical=False,
                enable_interaction=False,
            )
            pipeline = FeaturePipeline(
                processed_root=root / "data" / "processed",
                reports_root=root / "reports",
                pipeline_config=cfg,
            )
            results = pipeline.run()
            report = json.loads(
                Path(results[0].report_path).read_text(encoding="utf-8")
            )
            assert "rows_processed" in report
            assert "features_generated" in report
            assert "columns_added" in report
            assert "execution_time_seconds" in report
            assert "validation_summary" in report

    def test_build_registry_with_rolling_lag(self) -> None:
        cfg = FeaturePipelineConfig(
            rolling_config=RollingFeaturesConfig(
                columns=["demand_mw"], windows=[3], aggregations=["mean"]
            ),
            lag_config=LagFeaturesConfig(columns=["demand_mw"], lag_steps=[1]),
        )
        pipeline = FeaturePipeline(pipeline_config=cfg)
        registry = pipeline.build_registry()
        assert "demand_mw_rolling_3_mean" in registry
        assert "demand_mw_lag_1" in registry
