# GridSense AI - Data Dictionary Technical Reference

This document serves as the data dictionary placeholder and blueprint for the **GridSense AI** storage layer. It defines the structured dimensions, metrics, and relationships to be implemented in the data warehouse during subsequent ETL loading phases.

---

## 1. Purpose & Relationship with ETL
The Data Dictionary acts as a contract between the **API Ingestion Layer** (Phase 3) and the **ETL Database Loading Layer** (Phase 4). 
* **Validation Baseline:** Ingested raw JSON/CSV schemas must map to the column definitions, types, and constraints defined here.
* **Transform Reference:** The ETL pipeline reads this dictionary to structure raw arrays, cast datatypes, and build relational joins.
* **Traceability:** Establishes lineage tracing from raw data files on disk back to specific destination dimensions and facts.

---

## 2. Target Database Schema Structure
The data warehouse uses a Star Schema. Column requirements, nullability, and primary/foreign key definitions are detailed below.

### 2.1 Dimension Tables

#### DimState (Lookup Table)
* **StateID (Primary Key, INT):** Unique numeric identifier for each state/union territory.
* **Name (VARCHAR, NOT NULL):** Official state name.
* **Capital (VARCHAR, NOT NULL):** State capital city (used for weather queries).
* **Region (VARCHAR, NOT NULL):** Grid region zone ("Northern", "Western", "Southern", "Eastern", "North-Eastern").
* **Latitude (DECIMAL, NOT NULL):** WGS84 latitude coordinate.
* **Longitude (DECIMAL, NOT NULL):** WGS84 longitude coordinate.
* **Population (INT, NULL):** State population from Census 2011/estimates.
* **AreaSqKm (DECIMAL, NULL):** Land area in square kilometers.
* **UrbanPercent (DECIMAL, NULL):** Percentage of urbanized population.

#### DimDate (Calendar Dimensions)
* **DateKey (Primary Key, INT):** Integer formatted as `YYYYMMDD`.
* **CalendarDate (DATE, NOT NULL):** ISO 8601 date.
* **Year (INT, NOT NULL):** Calendar Year.
* **Month (INT, NOT NULL):** Month index (1-12).
* **Day (INT, NOT NULL):** Day of Month (1-31).
* **Weekday (VARCHAR, NOT NULL):** Day name (e.g. "Monday").
* **IsHoliday (BOOLEAN, NOT NULL):** True if date matches a national public holiday in India.
* **HolidayName (VARCHAR, NULL):** Name of holiday (e.g. "Republic Day").

---

### 2.2 Fact Tables

#### FactEnergyTelemetry (Time-Series Energy Metrics)
* **TelemetryID (Primary Key, INT, AUTOINCREMENT):** Unique identifier.
* **StateID (Foreign Key, INT):** References `DimState.StateID`.
* **DateKey (Foreign Key, INT):** References `DimDate.DateKey`.
* **TimestampHour (TEXT, NOT NULL):** ISO 8601 string in IST (e.g., `"2026-07-03T14:00:00+05:30"`).
* **DemandMW (DECIMAL, NULL):** Electricity demand.
* **SupplyMW (DECIMAL, NULL):** Energy supply dispatched.
* **SolarMW (DECIMAL, NULL):** Solar output.
* **WindMW (DECIMAL, NULL):** Wind output.
* **HydroMW (DECIMAL, NULL):** Hydro output.
* **CoalMW (DECIMAL, NULL):** Coal generation output.
* **GasMW (DECIMAL, NULL):** Gas generation output.

#### FactWeatherTelemetry (Atmospheric/AQI Metrics)
* **WeatherID (Primary Key, INT, AUTOINCREMENT):** Unique identifier.
* **StateID (Foreign Key, INT):** References `DimState.StateID`.
* **DateKey (Foreign Key, INT):** References `DimDate.DateKey`.
* **TimestampHour (TEXT, NOT NULL):** ISO 8601 string in IST.
* **TempC (DECIMAL, NULL):** Temperature in Celsius.
* **SolarIrrad (DECIMAL, NULL):** Solar radiation (GHI).
* **WindSpeed (DECIMAL, NULL):** Wind speed at 10 meters.
* **AQI (INT, NULL):** Air Quality Index.
* **PM25 (DECIMAL, NULL):** PM2.5 concentration.
* **PM10 (DECIMAL, NULL):** PM10 concentration.
* **NO2 (DECIMAL, NULL):** Nitrogen dioxide.
* **SO2 (DECIMAL, NULL):** Sulfur dioxide.
* **CO (DECIMAL, NULL):** Carbon monoxide.
* **O3 (DECIMAL, NULL):** Ozone.
* **SourceType (VARCHAR, NOT NULL):** Ingestion source classification (`'OBSERVATION'` vs `'FORECAST'`).

#### FactEnergyForecast (Prediction Targets)
* **ForecastID (Primary Key, INT, AUTOINCREMENT):** Unique identifier.
* **StateID (Foreign Key, INT):** References `DimState.StateID`.
* **DateKey (Foreign Key, INT):** References `DimDate.DateKey`.
* **TimestampHour (TEXT, NOT NULL):** Target forecast hour as an ISO 8601 string.
* **PredDemandMW (DECIMAL, NOT NULL):** ML model projected demand.
* **ModelVersion (VARCHAR, NOT NULL):** Version ID of the forecasting model.
