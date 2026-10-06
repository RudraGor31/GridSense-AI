"""Feature Engineering package for GridSense AI – Phase 4.3.

Transforms cleaned datasets (``data/processed/clean/``) into analytics-ready
feature datasets (``data/processed/features/``) that power dashboards, KPI
reports, statistical analyses, and machine-learning pipelines.

Public API
----------
- :class:`~src.features.feature_pipeline.FeaturePipeline` – orchestrator
- :class:`~src.features.feature_pipeline.FeaturePipelineResult` – run result
- :class:`~src.features.feature_registry.FeatureRegistry` – feature catalogue
- :class:`~src.features.feature_metadata.FeatureMetadata` – per-feature metadata
- :class:`~src.features.feature_validator.FeatureValidator` – quality checks
"""

from src.features.feature_metadata import FeatureMetadata
from src.features.feature_pipeline import FeaturePipeline, FeaturePipelineResult
from src.features.feature_registry import FeatureRegistry
from src.features.feature_validator import FeatureValidationResult, FeatureValidator

__all__ = [
    "FeatureMetadata",
    "FeaturePipeline",
    "FeaturePipelineResult",
    "FeatureRegistry",
    "FeatureValidationResult",
    "FeatureValidator",
]
