"""Weather-derived feature engineering for Phase 4.3.

Computes meteorological composite features from cleaned weather observations.
All formulas follow widely adopted meteorological standards.

Generated features
------------------
- ``heat_index``           – Apparent temperature at high humidity (°C).
- ``wind_chill``           – Apparent temperature at low temperature / high wind (°C).
- ``temperature_range``    – Daily temperature swing (requires ``temp_max`` & ``temp_min``) (°C).
- ``feels_like``           – Comfort index: heat index if hot & humid, wind chill if cold & windy (°C).
- ``humidity_category``    – "Low" / "Moderate" / "High" / "Very High".
- ``rain_category``        – "None" / "Light" / "Moderate" / "Heavy".
- ``wind_category``        – "Calm" / "Breeze" / "Moderate" / "Strong" / "Storm".
- ``weather_severity_score`` – 0-100 composite severity (higher = more severe).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.features.feature_metadata import FeatureMetadata

# ---------------------------------------------------------------------------
# Feature metadata
# ---------------------------------------------------------------------------

WEATHER_FEATURE_METADATA: List[FeatureMetadata] = [
    FeatureMetadata(
        name="heat_index",
        description="Apparent temperature accounting for humidity (Rothfusz equation).",
        formula="HI = -8.78469 + 1.61139411*T + 2.3385*RH - 0.14611*T*RH - ...",
        input_columns=["temperature_c", "humidity"],
        output_type="float",
        category="weather",
        unit="°C",
    ),
    FeatureMetadata(
        name="wind_chill",
        description="Apparent temperature accounting for wind speed (Environment Canada formula).",
        formula="WC = 13.12 + 0.6215*T - 11.37*V^0.16 + 0.3965*T*V^0.16",
        input_columns=["temperature_c", "wind_speed"],
        output_type="float",
        category="weather",
        unit="°C",
    ),
    FeatureMetadata(
        name="temperature_range",
        description="Difference between maximum and minimum temperature for the period.",
        formula="temp_max - temp_min",
        input_columns=["temp_max", "temp_min"],
        output_type="float",
        category="weather",
        unit="°C",
    ),
    FeatureMetadata(
        name="feels_like",
        description="Human comfort index: heat_index when T>=27°C & RH>=40%, wind_chill when T<10°C & V>4.8, else T.",
        formula="heat_index if hot_humid else wind_chill if cold_windy else temperature_c",
        input_columns=["temperature_c", "humidity", "wind_speed"],
        output_type="float",
        category="weather",
        unit="°C",
    ),
    FeatureMetadata(
        name="humidity_category",
        description="Categorical humidity level based on relative humidity %.",
        formula="Low(<30) | Moderate(30-60) | High(60-80) | Very High(>80)",
        input_columns=["humidity"],
        output_type="str",
        category="weather",
        unit="",
    ),
    FeatureMetadata(
        name="rain_category",
        description="Categorical rainfall intensity.",
        formula="None(<0.1mm) | Light(0.1-2.5mm) | Moderate(2.5-10mm) | Heavy(>10mm)",
        input_columns=["rainfall"],
        output_type="str",
        category="weather",
        unit="",
    ),
    FeatureMetadata(
        name="wind_category",
        description="Beaufort-inspired wind category based on km/h.",
        formula="Calm(<5) | Breeze(5-20) | Moderate(20-40) | Strong(40-75) | Storm(>75)",
        input_columns=["wind_speed"],
        output_type="str",
        category="weather",
        unit="",
    ),
    FeatureMetadata(
        name="weather_severity_score",
        description="Composite 0-100 severity score combining temperature deviation, wind, and rainfall.",
        formula="0.4*temp_score + 0.3*wind_score + 0.3*rain_score",
        input_columns=["temperature_c", "wind_speed", "rainfall"],
        output_type="float",
        category="weather",
        unit="",
    ),
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class WeatherFeaturesConfig:
    """Configuration for weather feature generation.

    Attributes
    ----------
    temperature_column:
        Column holding temperature in °C.
    humidity_column:
        Column holding relative humidity in %.
    wind_speed_column:
        Column holding wind speed in km/h.
    rainfall_column:
        Column holding rainfall in mm.
    temp_max_column:
        Column holding daily maximum temperature in °C.
    temp_min_column:
        Column holding daily minimum temperature in °C.
    reference_temperature:
        Comfortable reference temperature used in severity scoring (°C).
    """

    temperature_column: str = "temperature_c"
    humidity_column: str = "humidity"
    wind_speed_column: str = "wind_speed"
    rainfall_column: str = "rainfall"
    temp_max_column: str = "temp_max"
    temp_min_column: str = "temp_min"
    reference_temperature: float = 22.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _heat_index(temp_c: float, rh: float) -> float:
    """Compute heat index using the Rothfusz regression (°C).

    Valid for T >= 27°C and RH >= 40%.  Returns *temp_c* unchanged outside
    that range.

    Parameters
    ----------
    temp_c:
        Dry-bulb temperature in °C.
    rh:
        Relative humidity in %.

    Returns
    -------
    float
        Heat index in °C.
    """
    if temp_c < 27.0 or rh < 40.0:
        return temp_c
    # Convert to Fahrenheit for the Rothfusz equation
    tf = temp_c * 9.0 / 5.0 + 32.0
    hi_f = (
        -42.379
        + 2.04901523 * tf
        + 10.14333127 * rh
        - 0.22475541 * tf * rh
        - 0.00683783 * tf * tf
        - 0.05481717 * rh * rh
        + 0.00122874 * tf * tf * rh
        + 0.00085282 * tf * rh * rh
        - 0.00000199 * tf * tf * rh * rh
    )
    return round((hi_f - 32.0) * 5.0 / 9.0, 2)


def _wind_chill(temp_c: float, wind_kmh: float) -> float:
    """Compute wind chill (Environment Canada / NOAA formula) in °C.

    Valid for T <= 10°C and V >= 4.8 km/h.  Returns *temp_c* unchanged outside
    that range.

    Parameters
    ----------
    temp_c:
        Air temperature in °C.
    wind_kmh:
        Wind speed in km/h.

    Returns
    -------
    float
        Wind chill in °C.
    """
    if temp_c > 10.0 or wind_kmh < 4.8:
        return temp_c
    v016 = wind_kmh**0.16
    wc = 13.12 + 0.6215 * temp_c - 11.37 * v016 + 0.3965 * temp_c * v016
    return round(wc, 2)


def _humidity_category(rh: float) -> str:
    if rh < 30.0:
        return "Low"
    if rh < 60.0:
        return "Moderate"
    if rh < 80.0:
        return "High"
    return "Very High"


def _rain_category(mm: float) -> str:
    if mm < 0.1:
        return "None"
    if mm < 2.5:
        return "Light"
    if mm < 10.0:
        return "Moderate"
    return "Heavy"


def _wind_category(kmh: float) -> str:
    if kmh < 5.0:
        return "Calm"
    if kmh < 20.0:
        return "Breeze"
    if kmh < 40.0:
        return "Moderate"
    if kmh < 75.0:
        return "Strong"
    return "Storm"


def _severity_score(
    temp_c: float, wind_kmh: float, rain_mm: float, ref_temp: float
) -> float:
    """Compute a 0-100 weather severity composite score."""
    temp_dev = min(abs(temp_c - ref_temp) / 30.0, 1.0)  # normalise to [0,1]
    wind_score = min(wind_kmh / 100.0, 1.0)
    rain_score = min(rain_mm / 50.0, 1.0)
    raw = (0.4 * temp_dev + 0.3 * wind_score + 0.3 * rain_score) * 100.0
    return round(min(max(raw, 0.0), 100.0), 2)


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_weather_features(
    records: List[Dict[str, Any]],
    config: Optional[WeatherFeaturesConfig] = None,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Add weather composite feature columns to every record.

    Parameters
    ----------
    records:
        Mutable list of record dictionaries (modified in-place).
    config:
        :class:`WeatherFeaturesConfig`.  Defaults to column-name defaults.

    Returns
    -------
    tuple[list[dict], list[str], list[str]]
        ``(records, added_columns, warnings)``
    """
    cfg = config or WeatherFeaturesConfig()
    added: set[str] = set()
    warnings: List[str] = []

    for row_idx, record in enumerate(records):
        temp = _safe_float(record.get(cfg.temperature_column))
        rh = _safe_float(record.get(cfg.humidity_column))
        wind = _safe_float(record.get(cfg.wind_speed_column))
        rain = _safe_float(record.get(cfg.rainfall_column))
        t_max = _safe_float(record.get(cfg.temp_max_column))
        t_min = _safe_float(record.get(cfg.temp_min_column))

        # heat_index
        if temp is not None and rh is not None:
            record["heat_index"] = _heat_index(temp, rh)
        else:
            record["heat_index"] = None
            if temp is None or rh is None:
                warnings.append(
                    f"heat_index skipped at row {row_idx}: missing temp or humidity"
                )
        added.add("heat_index")

        # wind_chill
        if temp is not None and wind is not None:
            record["wind_chill"] = _wind_chill(temp, wind)
        else:
            record["wind_chill"] = None
        added.add("wind_chill")

        # temperature_range
        if t_max is not None and t_min is not None:
            record["temperature_range"] = round(t_max - t_min, 2)
        else:
            record["temperature_range"] = None
        added.add("temperature_range")

        # feels_like
        if temp is not None:
            hi_val = record.get("heat_index")
            wc_val = record.get("wind_chill")
            if temp >= 27.0 and rh is not None and rh >= 40.0 and hi_val is not None:
                record["feels_like"] = hi_val
            elif (
                temp <= 10.0 and wind is not None and wind >= 4.8 and wc_val is not None
            ):
                record["feels_like"] = wc_val
            else:
                record["feels_like"] = round(temp, 2)
        else:
            record["feels_like"] = None
        added.add("feels_like")

        # humidity_category
        if rh is not None:
            record["humidity_category"] = _humidity_category(rh)
        else:
            record["humidity_category"] = None
        added.add("humidity_category")

        # rain_category
        if rain is not None:
            record["rain_category"] = _rain_category(rain)
        else:
            record["rain_category"] = None
        added.add("rain_category")

        # wind_category
        if wind is not None:
            record["wind_category"] = _wind_category(wind)
        else:
            record["wind_category"] = None
        added.add("wind_category")

        # weather_severity_score
        if temp is not None and wind is not None and rain is not None:
            record["weather_severity_score"] = _severity_score(
                temp, wind, rain, cfg.reference_temperature
            )
        else:
            record["weather_severity_score"] = None
        added.add("weather_severity_score")

    return records, sorted(added), warnings
