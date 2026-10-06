"""Feature registry for Phase 4.3.

The :class:`FeatureRegistry` maintains a catalogue of all available engineered
features.  It maps feature names to :class:`~src.features.feature_metadata.FeatureMetadata`
descriptors and enforces uniqueness, dependency ordering, and category grouping.

Design
------
- Central singleton-style registry per pipeline execution.
- Supports lookup by name, category, and tag.
- Raises ``KeyError`` on duplicate registration (fail-fast).
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from src.features.feature_metadata import FeatureMetadata


class FeatureRegistry:
    """Catalogue of all engineered feature metadata.

    Parameters
    ----------
    strict:
        If ``True`` (default), registering a duplicate feature name raises
        ``KeyError``.  If ``False``, subsequent registrations silently overwrite.

    Examples
    --------
    >>> registry = FeatureRegistry()
    >>> registry.register(FeatureMetadata(name="heat_index", ...))
    >>> meta = registry.get("heat_index")
    """

    def __init__(self, strict: bool = True) -> None:
        self._strict = strict
        self._catalogue: Dict[str, FeatureMetadata] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, metadata: FeatureMetadata) -> None:
        """Register a feature descriptor.

        Parameters
        ----------
        metadata:
            :class:`~src.features.feature_metadata.FeatureMetadata` instance.

        Raises
        ------
        KeyError
            If ``strict=True`` and a feature with the same name already exists.
        """
        if self._strict and metadata.name in self._catalogue:
            raise KeyError(
                f"Feature '{metadata.name}' is already registered. "
                "Use strict=False to allow overwriting."
            )
        self._catalogue[metadata.name] = metadata

    def register_many(self, metadata_list: List[FeatureMetadata]) -> None:
        """Convenience wrapper to register multiple features at once.

        Parameters
        ----------
        metadata_list:
            Iterable of :class:`~src.features.feature_metadata.FeatureMetadata`.
        """
        for metadata in metadata_list:
            self.register(metadata)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[FeatureMetadata]:
        """Return the metadata for *name*, or ``None`` if not found.

        Parameters
        ----------
        name:
            Feature name to look up.

        Returns
        -------
        FeatureMetadata | None
        """
        return self._catalogue.get(name)

    def require(self, name: str) -> FeatureMetadata:
        """Return the metadata for *name*, raising if not found.

        Parameters
        ----------
        name:
            Feature name to look up.

        Returns
        -------
        FeatureMetadata

        Raises
        ------
        KeyError
            If *name* is not registered.
        """
        if name not in self._catalogue:
            raise KeyError(f"Feature '{name}' is not registered.")
        return self._catalogue[name]

    def by_category(self, category: str) -> List[FeatureMetadata]:
        """Return all features belonging to *category*.

        Parameters
        ----------
        category:
            Category string to filter by (case-sensitive).

        Returns
        -------
        list[FeatureMetadata]
        """
        return [m for m in self._catalogue.values() if m.category == category]

    def by_tag(self, tag: str) -> List[FeatureMetadata]:
        """Return all features that carry *tag*.

        Parameters
        ----------
        tag:
            Tag string to search for.

        Returns
        -------
        list[FeatureMetadata]
        """
        return [m for m in self._catalogue.values() if tag in m.tags]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def names(self) -> List[str]:
        """Return all registered feature names in insertion order.

        Returns
        -------
        list[str]
        """
        return list(self._catalogue.keys())

    def all(self) -> List[FeatureMetadata]:
        """Return all registered metadata instances.

        Returns
        -------
        list[FeatureMetadata]
        """
        return list(self._catalogue.values())

    def categories(self) -> List[str]:
        """Return deduplicated list of registered categories.

        Returns
        -------
        list[str]
        """
        seen: List[str] = []
        for m in self._catalogue.values():
            if m.category not in seen:
                seen.append(m.category)
        return seen

    def __len__(self) -> int:
        return len(self._catalogue)

    def __contains__(self, name: object) -> bool:
        return name in self._catalogue

    def __iter__(self) -> Iterator[FeatureMetadata]:
        return iter(self._catalogue.values())

    def clear(self) -> None:
        """Remove all registrations (useful between test runs)."""
        self._catalogue.clear()
