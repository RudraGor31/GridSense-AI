"""Feature metadata dataclass for Phase 4.3.

Every engineered feature must carry a :class:`FeatureMetadata` descriptor so
the feature catalogue remains self-documenting and traceable.  Metadata is
written alongside feature datasets in ``reports/features/metadata/``.

Design
------
- Immutable once constructed (``frozen=True``).
- Serialisable to/from plain dicts for JSON persistence.
- Versioned so that downstream consumers can detect breaking changes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    """Return current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class FeatureMetadata:
    """Descriptor for a single engineered feature.

    Attributes
    ----------
    name:
        Unique snake_case feature name, e.g. ``"heat_index"``.
    description:
        Human-readable explanation of what the feature represents.
    formula:
        Mathematical or algorithmic formula used to compute the feature.
    input_columns:
        Source column names required to compute this feature.
    output_type:
        Python type name of the produced value, e.g. ``"float"``, ``"int"``,
        ``"str"``, ``"bool"``.
    category:
        High-level grouping: ``"time"``, ``"weather"``, ``"energy"``,
        ``"air_quality"``, ``"rolling"``, ``"lag"``, ``"statistical"``,
        ``"interaction"``.
    dependencies:
        Other feature names that must be computed before this one.
    version:
        Semantic version string, e.g. ``"1.0.0"``.
    created_at:
        UTC ISO-8601 timestamp of first registration.
    tags:
        Optional free-form labels for search and filtering.
    unit:
        Physical unit of the output value, e.g. ``"°C"``, ``"MW"``, ``"%"``.
    """

    name: str
    description: str
    formula: str
    input_columns: List[str]
    output_type: str
    category: str
    dependencies: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    created_at: str = field(default_factory=_now_iso)
    tags: List[str] = field(default_factory=list)
    unit: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary suitable for JSON output.

        Returns
        -------
        dict[str, Any]
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeatureMetadata":
        """Deserialise from a plain dictionary.

        Parameters
        ----------
        data:
            Dictionary previously produced by :meth:`to_dict`.

        Returns
        -------
        FeatureMetadata
        """
        return cls(
            name=data["name"],
            description=data["description"],
            formula=data["formula"],
            input_columns=data.get("input_columns", []),
            output_type=data.get("output_type", "float"),
            category=data.get("category", ""),
            dependencies=data.get("dependencies", []),
            version=data.get("version", "1.0.0"),
            created_at=data.get("created_at", _now_iso()),
            tags=data.get("tags", []),
            unit=data.get("unit", ""),
        )


def write_metadata_report(
    metadata_list: List[FeatureMetadata],
    reports_root: Path,
    dataset_name: str,
    run_timestamp: Optional[str] = None,
) -> Path:
    """Write a metadata catalogue JSON file to ``reports/features/metadata/``.

    Parameters
    ----------
    metadata_list:
        All :class:`FeatureMetadata` instances for this pipeline run.
    reports_root:
        Root of the reports tree.
    dataset_name:
        Dataset identifier used as part of the file name.
    run_timestamp:
        UTC ISO-8601 string identifying this run (defaults to now).

    Returns
    -------
    Path
        Absolute path to the written JSON file.
    """
    ts = run_timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_dir = reports_root / "features" / "metadata"
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{dataset_name}_{ts}.json"
    payload = {
        "dataset": dataset_name,
        "generated_at": _now_iso(),
        "total_features": len(metadata_list),
        "features": [m.to_dict() for m in metadata_list],
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return output_path
