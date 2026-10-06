"""Feature pipeline orchestrator for Phase 4.3.

:class:`FeaturePipeline` reads clean datasets from
``data/processed/clean/<dataset>/``, applies a configuration-driven sequence
of feature engineering steps, validates the output, and writes:

- Feature dataset JSON → ``data/processed/features/<dataset>/<stem>.json``
- Feature report JSON  → ``reports/features/<dataset>_<timestamp>.json``
- Metadata catalogue   → ``reports/features/metadata/<dataset>_<timestamp>.json``

Pipeline step order
-------------------
1. Time features          – calendar / cyclical temporal features.
2. Weather features       – meteorological composite indices.
3. Energy features        – demand KPIs and business flags.
4. AQI features           – air-quality tiers and trends.
5. Statistical features   – global and incremental statistics.
6. Rolling features       – sliding-window aggregations.
7. Lag features           – time-shifted copies.
8. Interaction features   – multiplicative cross-feature terms.
9. Validation             – quality checks on all generated features.
10. Write outputs          – atomically persist feature dataset + reports.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.config import config
from src.features.air_quality_features import AQIFeaturesConfig, add_aqi_features
from src.features.energy_features import EnergyFeaturesConfig, add_energy_features
from src.features.feature_metadata import FeatureMetadata, write_metadata_report
from src.features.feature_registry import FeatureRegistry
from src.features.feature_validator import FeatureValidationResult, FeatureValidator
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
from src.utils.helpers import save_file_atomically
from src.utils.logging_util import logger

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class FeaturePipelineResult:
    """Result of one feature pipeline run.

    Attributes
    ----------
    dataset_name:
        Name of the processed dataset.
    rows_processed:
        Number of records that passed through the pipeline.
    features_added:
        List of all feature column names added.
    feature_count:
        Number of new feature columns added.
    feature_file_path:
        Absolute path to the written feature JSON file.
    report_path:
        Absolute path to the written feature report JSON file.
    metadata_path:
        Absolute path to the written feature metadata JSON file.
    execution_time_seconds:
        Wall-clock time for the complete pipeline run.
    validation_result:
        :class:`~src.features.feature_validator.FeatureValidationResult` from
        the post-generation quality check.
    warnings:
        Non-fatal issues emitted during feature generation.
    errors:
        Fatal issues encountered.
    """

    dataset_name: str
    rows_processed: int
    features_added: List[str]
    feature_count: int
    feature_file_path: str
    report_path: str
    metadata_path: str
    execution_time_seconds: float
    validation_result: Optional[FeatureValidationResult] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline configuration
# ---------------------------------------------------------------------------


@dataclass
class FeaturePipelineConfig:
    """Top-level configuration for the feature pipeline.

    Attributes
    ----------
    time_config:
        Configuration for time feature generation.
    weather_config:
        Configuration for weather feature generation.
    energy_config:
        Configuration for energy feature generation.
    aqi_config:
        Configuration for AQI feature generation.
    statistical_config:
        Configuration for statistical feature generation.
    rolling_config:
        Configuration for rolling window features.
    lag_config:
        Configuration for lag features.
    interaction_config:
        Configuration for interaction features.
    enable_time:
        Whether to run the time feature step.
    enable_weather:
        Whether to run the weather feature step.
    enable_energy:
        Whether to run the energy feature step.
    enable_aqi:
        Whether to run the AQI feature step.
    enable_statistical:
        Whether to run the statistical feature step.
    enable_rolling:
        Whether to run the rolling feature step.
    enable_lag:
        Whether to run the lag feature step.
    enable_interaction:
        Whether to run the interaction feature step.
    validator_numeric_columns:
        Columns treated as numeric during validation.
    validator_range_bounds:
        Per-column expected numeric ranges for validation.
    """

    time_config: Optional[TimeFeaturesConfig] = None
    weather_config: Optional[WeatherFeaturesConfig] = None
    energy_config: Optional[EnergyFeaturesConfig] = None
    aqi_config: Optional[AQIFeaturesConfig] = None
    statistical_config: Optional[StatisticalFeaturesConfig] = None
    rolling_config: Optional[RollingFeaturesConfig] = None
    lag_config: Optional[LagFeaturesConfig] = None
    interaction_config: Optional[InteractionFeaturesConfig] = None

    enable_time: bool = True
    enable_weather: bool = True
    enable_energy: bool = True
    enable_aqi: bool = True
    enable_statistical: bool = True
    enable_rolling: bool = True
    enable_lag: bool = True
    enable_interaction: bool = True

    validator_numeric_columns: List[str] = field(default_factory=list)
    validator_range_bounds: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class FeaturePipeline:
    """Orchestrate config-driven feature engineering across clean datasets.

    Parameters
    ----------
    processed_root:
        Root of the processed data tree.  Defaults to
        ``config.processed_data_dir``.
    reports_root:
        Root of the reports tree.  Defaults to ``config.reports_dir``.
    pipeline_config:
        Top-level pipeline configuration.

    Examples
    --------
    >>> pipeline = FeaturePipeline()
    >>> results = pipeline.run(dataset_filter=["weather"])
    >>> for r in results:
    ...     print(r.dataset_name, r.feature_count)
    """

    def __init__(
        self,
        processed_root: Optional[Path] = None,
        reports_root: Optional[Path] = None,
        pipeline_config: Optional[FeaturePipelineConfig] = None,
    ) -> None:
        self.processed_root = processed_root or Path(config.processed_data_dir)
        self.reports_root = reports_root or Path(config.reports_dir)
        self.pipeline_config = pipeline_config or FeaturePipelineConfig()

        self.clean_root = self.processed_root / "clean"
        self.features_root = self.processed_root / "features"
        self.features_root.mkdir(parents=True, exist_ok=True)
        self.reports_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public run method
    # ------------------------------------------------------------------

    def run(
        self, dataset_filter: Optional[List[str]] = None
    ) -> List[FeaturePipelineResult]:
        """Run the feature pipeline across all clean datasets.

        Parameters
        ----------
        dataset_filter:
            If provided, only datasets in this list (lower-case) are processed.

        Returns
        -------
        list[FeaturePipelineResult]
        """
        results: List[FeaturePipelineResult] = []
        for dataset_dir in sorted(self.clean_root.glob("*")):
            if not dataset_dir.is_dir():
                continue
            dataset_name = dataset_dir.name.lower()
            if dataset_filter and dataset_name not in {
                d.lower() for d in dataset_filter
            }:
                continue
            for file_path in sorted(dataset_dir.glob("*.json")):
                result = self._process_file(dataset_name, file_path)
                results.append(result)
        return results

    # ------------------------------------------------------------------
    # Per-file processing
    # ------------------------------------------------------------------

    def _process_file(
        self, dataset_name: str, file_path: Path
    ) -> FeaturePipelineResult:
        start = time.perf_counter()
        warnings: List[str] = []
        errors: List[str] = []
        all_metadata: List[FeatureMetadata] = []
        all_added: List[str] = []
        cfg = self.pipeline_config

        records = self._read_clean_file(file_path)

        # ------------------------------------------------------------------
        # Step 1 – Time features
        # ------------------------------------------------------------------
        if cfg.enable_time:
            records, added, step_warnings = add_time_features(records, cfg.time_config)
            all_added.extend(c for c in added if c not in all_added)
            warnings.extend(step_warnings)

        # ------------------------------------------------------------------
        # Step 2 – Weather features
        # ------------------------------------------------------------------
        if cfg.enable_weather:
            records, added, step_warnings = add_weather_features(
                records, cfg.weather_config
            )
            all_added.extend(c for c in added if c not in all_added)
            warnings.extend(step_warnings)

        # ------------------------------------------------------------------
        # Step 3 – Energy features
        # ------------------------------------------------------------------
        if cfg.enable_energy:
            records, added, step_warnings = add_energy_features(
                records, cfg.energy_config
            )
            all_added.extend(c for c in added if c not in all_added)
            warnings.extend(step_warnings)

        # ------------------------------------------------------------------
        # Step 4 – AQI features
        # ------------------------------------------------------------------
        if cfg.enable_aqi:
            records, added, step_warnings = add_aqi_features(records, cfg.aqi_config)
            all_added.extend(c for c in added if c not in all_added)
            warnings.extend(step_warnings)

        # ------------------------------------------------------------------
        # Step 5 – Statistical features
        # ------------------------------------------------------------------
        if cfg.enable_statistical and cfg.statistical_config:
            records, added, step_warnings = add_statistical_features(
                records, cfg.statistical_config
            )
            all_added.extend(c for c in added if c not in all_added)
            warnings.extend(step_warnings)
            all_metadata.extend(
                build_statistical_metadata(
                    cfg.statistical_config.columns,
                    cfg.statistical_config.moving_avg_span,
                )
            )

        # ------------------------------------------------------------------
        # Step 6 – Rolling features
        # ------------------------------------------------------------------
        if cfg.enable_rolling and cfg.rolling_config:
            records, added, step_warnings = add_rolling_features(
                records, cfg.rolling_config
            )
            all_added.extend(c for c in added if c not in all_added)
            warnings.extend(step_warnings)
            all_metadata.extend(
                build_rolling_metadata(
                    cfg.rolling_config.columns,
                    cfg.rolling_config.windows,
                    cfg.rolling_config.aggregations,
                )
            )

        # ------------------------------------------------------------------
        # Step 7 – Lag features
        # ------------------------------------------------------------------
        if cfg.enable_lag and cfg.lag_config:
            records, added, step_warnings = add_lag_features(records, cfg.lag_config)
            all_added.extend(c for c in added if c not in all_added)
            warnings.extend(step_warnings)
            all_metadata.extend(
                build_lag_metadata(
                    cfg.lag_config.columns,
                    cfg.lag_config.lag_steps,
                )
            )

        # ------------------------------------------------------------------
        # Step 8 – Interaction features
        # ------------------------------------------------------------------
        if cfg.enable_interaction and cfg.interaction_config:
            records, added, step_warnings = add_interaction_features(
                records, cfg.interaction_config
            )
            all_added.extend(c for c in added if c not in all_added)
            warnings.extend(step_warnings)
            all_metadata.extend(
                build_interaction_metadata(
                    cfg.interaction_config.interactions,
                    cfg.interaction_config.scale,
                )
            )

        # ------------------------------------------------------------------
        # Step 9 – Validation
        # ------------------------------------------------------------------
        validator = FeatureValidator(
            numeric_columns=cfg.validator_numeric_columns or all_added,
            range_bounds=cfg.validator_range_bounds,
        )
        validation_result = validator.validate(records, dataset_name, all_added)
        if not validation_result.is_valid:
            errors.extend(validation_result.errors)

        # ------------------------------------------------------------------
        # Step 10 – Write outputs
        # ------------------------------------------------------------------
        execution_time = round(time.perf_counter() - start, 4)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        feature_file = self._write_feature_dataset(
            dataset_name, file_path.stem, records
        )
        report_path = self._write_feature_report(
            dataset_name,
            ts,
            len(records),
            all_added,
            execution_time,
            warnings,
            errors,
            validation_result,
        )
        metadata_path = write_metadata_report(
            all_metadata, self.reports_root, dataset_name, ts
        )

        logger.info(
            "Feature engineering | dataset=%s | rows=%s | features=%s | time=%.4fs | warnings=%s",
            dataset_name,
            len(records),
            len(all_added),
            execution_time,
            len(warnings),
        )

        return FeaturePipelineResult(
            dataset_name=dataset_name,
            rows_processed=len(records),
            features_added=all_added,
            feature_count=len(all_added),
            feature_file_path=str(feature_file),
            report_path=str(report_path),
            metadata_path=str(metadata_path),
            execution_time_seconds=execution_time,
            validation_result=validation_result,
            warnings=warnings,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # I/O helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_clean_file(file_path: Path) -> List[Dict[str, Any]]:
        """Read a clean JSON envelope and return its rows list.

        Parameters
        ----------
        file_path:
            Path to the clean ``.json`` file produced by Phase 4.2.

        Returns
        -------
        list[dict]
        """
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        # Support both envelope format {"rows": [...]} and bare list
        if isinstance(payload, list):
            return payload
        return payload.get("rows", [])

    def _write_feature_dataset(
        self, dataset_name: str, source_stem: str, records: List[Dict[str, Any]]
    ) -> Path:
        """Write feature dataset to ``data/processed/features/<dataset>/``.

        Parameters
        ----------
        dataset_name:
            Dataset identifier.
        source_stem:
            Stem of the source clean filename.
        records:
            Feature-enriched records.

        Returns
        -------
        Path
        """
        dataset_dir = self.features_root / dataset_name
        dataset_dir.mkdir(parents=True, exist_ok=True)
        output_path = dataset_dir / f"{source_stem}.json"
        payload = {
            "dataset": dataset_name,
            "engineered_at": time.time(),
            "rows": records,
        }
        save_file_atomically(
            json.dumps(payload, indent=2, ensure_ascii=False), output_path
        )
        return output_path

    def _write_feature_report(
        self,
        dataset_name: str,
        ts: str,
        rows: int,
        added_columns: List[str],
        execution_time: float,
        warnings: List[str],
        errors: List[str],
        validation: Optional[FeatureValidationResult],
    ) -> Path:
        """Write a feature report JSON to ``reports/features/``.

        Returns
        -------
        Path
        """
        report_dir = self.reports_root / "features"
        report_dir.mkdir(parents=True, exist_ok=True)
        output_path = report_dir / f"{dataset_name}_{ts}.json"
        payload: Dict[str, Any] = {
            "dataset": dataset_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rows_processed": rows,
            "features_generated": len(added_columns),
            "columns_added": added_columns,
            "execution_time_seconds": execution_time,
            "warnings": warnings,
            "errors": errors,
        }
        if validation:
            payload["validation_summary"] = {
                "is_valid": validation.is_valid,
                "missing_count": validation.missing_count,
                "infinite_count": validation.infinite_count,
                "nan_count": validation.nan_count,
                "out_of_range_count": validation.out_of_range_count,
                "duplicate_columns": validation.duplicate_columns,
                "invalid_calc_count": validation.invalid_calc_count,
                "warnings": validation.warnings[:20],  # cap at 20 for readability
            }
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return output_path

    # ------------------------------------------------------------------
    # Registry integration
    # ------------------------------------------------------------------

    def build_registry(self) -> FeatureRegistry:
        """Build a :class:`~src.features.feature_registry.FeatureRegistry`
        pre-populated with all features this pipeline is configured to generate.

        Returns
        -------
        FeatureRegistry
        """
        registry = FeatureRegistry(strict=False)
        cfg = self.pipeline_config

        # Dynamically-named features
        if cfg.statistical_config:
            registry.register_many(
                build_statistical_metadata(
                    cfg.statistical_config.columns,
                    cfg.statistical_config.moving_avg_span,
                )
            )
        if cfg.rolling_config:
            registry.register_many(
                build_rolling_metadata(
                    cfg.rolling_config.columns,
                    cfg.rolling_config.windows,
                    cfg.rolling_config.aggregations,
                )
            )
        if cfg.lag_config:
            registry.register_many(
                build_lag_metadata(
                    cfg.lag_config.columns,
                    cfg.lag_config.lag_steps,
                )
            )
        if cfg.interaction_config:
            registry.register_many(
                build_interaction_metadata(
                    cfg.interaction_config.interactions,
                    cfg.interaction_config.scale,
                )
            )
        return registry
