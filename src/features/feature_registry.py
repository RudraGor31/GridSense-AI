"""Feature registry for Phase 4.3 – central catalogue of all engineered features.

The :class:`FeatureRegistry` acts as a singleton catalogue that maps feature
names to their :class:`~src.features.feature_metadata.FeatureMetadata` records.
Generators register their features upon construction; the pipeline uses the
registry to produce documentation, lineage reports, and validation rules.

Design
------
- Registration is additive and idempotent: re-registering a feature with the
  same name and version is a no-op; re-registering with a different version
  replaces the entry and logs a warning.
- The registry is not a database — it lives in-process.  Persistence is handled
  by :func:`~src.features.feature_metadata.write_feature_metadata`.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from src.features.feature_metadata import FeatureMetadata
from src.utils.logging_util import logger


class FeatureRegistry:
    """In-process catalogue of all registered feature metadata.

    Parameters
    ----------
    None — use the module-level singleton :data:`registry` in most cases.

    Examples
    --------
    >>> from src.features.feature_registry import registry
    >>> registry.register(FeatureMetadata(name="heat_index", ...))
    >>> meta = registry.get("heat_index")
    """

    def __init__(self) -> None:
        self._store: Dict[str, FeatureMetadata] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, metadata: FeatureMetadata) -> None:
        """Register a feature.

        If the feature name already exists with the same version the call is
        a no-op.  If the version differs the entry is replaced and a warning
        is emitted.

        Parameters
        ----------
        metadata:
            Fully populated :class:`FeatureMetadata` instance.
        """
        existing = self._store.get(metadata.name)
        if existing is not None:
            if existing.version == metadata.version:
                return  # idempotent
            logger.warning(
                "Feature registry: replacing '%s' v%s with v%s",
                metadata.name,
                existing.version,
                metadata.version,
            )
        self._store[metadata.name] = metadata

    def register_many(self, metadata_list: List[FeatureMetadata]) -> None:
        """Register multiple features at once.

        Parameters
        ----------
        metadata_list:
            Iterable of :class:`FeatureMetadata` instances.
        """
        for meta in metadata_list:
            self.register(meta)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[FeatureMetadata]:
        """Return metadata for *name*, or ``None`` if not registered.

        Parameters
        ----------
        name:
            Feature column name (snake_case).

        Returns
        -------
        FeatureMetadata | None
        """
        return self._store.get(name)

    def all_metadata(self) -> List[FeatureMetadata]:
        """Return all registered metadata records, sorted by name.

        Returns
        -------
        list[FeatureMetadata]
        """
        return sorted(self._store.values(), key=lambda m: m.name)

    def by_category(self, category: str) -> List[FeatureMetadata]:
        """Return all features belonging to *category*.

        Parameters
        ----------
        category:
            Category slug (e.g. ``"weather"``, ``"energy"``, ``"time"``).

        Returns
        -------
        list[FeatureMetadata]
        """
        return [m for m in self._store.values() if m.category == category]

    def names(self) -> List[str]:
        """Return all registered feature names in sorted order.

        Returns
        -------
        list[str]
        """
        return sorted(self._store.keys())

    def __len__(self) -> int:
        return len(self._store)

    def __iter__(self) -> Iterator[FeatureMetadata]:
        return iter(self.all_metadata())

    def __contains__(self, name: object) -> bool:
        return name in self._store

    def clear(self) -> None:
        """Clear all registered features (useful for test isolation)."""
        self._store.clear()


# ---------------------------------------------------------------------------
# Module-level singleton — import this in generators and the pipeline
# ---------------------------------------------------------------------------

#: Global feature registry instance shared across all feature generators.
registry: FeatureRegistry = FeatureRegistry()
