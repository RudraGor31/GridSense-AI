"""Duplicate detection and row-level deduplication for Phase 4.2.

Provides :func:`handle_duplicates` which applies one of three strategies to a
list of record dictionaries.  Duplicate detection is based on a deterministic
JSON serialisation of the entire row (all keys sorted), so two rows are
considered duplicate if and only if they are structurally identical.

Strategies
----------
- ``keep_first``  – Retain the first occurrence; drop all later duplicates.
- ``keep_last``   – Retain the last occurrence; drop all earlier duplicates.
- ``drop_all``    – Remove every row that appears more than once.

Every removed row emits an :class:`~src.etl.audit.AuditRecord` so the
deduplication is fully auditable.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List, Tuple

from src.etl.audit import AuditRecord


def _row_key(record: Dict[str, Any]) -> str:
    """Return a deterministic string key for *record*.

    The key is the JSON representation with all keys sorted lexicographically,
    which guarantees that two structurally identical rows produce the same key
    regardless of insertion order.

    Parameters
    ----------
    record:
        A single dataset row.

    Returns
    -------
    str
    """
    return json.dumps(record, sort_keys=True, ensure_ascii=False)


def handle_duplicates(
    records: List[Dict[str, Any]],
    dataset_name: str,
    strategy: str,
) -> Tuple[List[Dict[str, Any]], int, List[AuditRecord], List[str]]:
    """Detect and handle duplicate rows according to *strategy*.

    Parameters
    ----------
    records:
        Mutable list of record dictionaries representing the staging dataset.
    dataset_name:
        Dataset identifier used in audit records.
    strategy:
        One of ``"keep_first"``, ``"keep_last"``, or ``"drop_all"``.

    Returns
    -------
    tuple[list[dict], int, list[AuditRecord], list[str]]
        ``(deduplicated_records, removed_count, audit_records, warnings)``

        - *deduplicated_records*: Records after deduplication.
        - *removed_count*:        Number of rows removed.
        - *audit_records*:        One record per removed row.
        - *warnings*:             Non-fatal issues (e.g. unknown strategy).
    """
    warnings: List[str] = []
    audit: List[AuditRecord] = []

    if not records:
        return records, 0, audit, warnings

    keys = [_row_key(record) for record in records]
    counts: Counter[str] = Counter(keys)
    removed = 0

    # ------------------------------------------------------------------
    # KEEP FIRST – drop duplicates encountered after the first occurrence
    # ------------------------------------------------------------------
    if strategy == "keep_first":
        seen: set[str] = set()
        kept: List[Dict[str, Any]] = []
        for idx, record in enumerate(records):
            key = keys[idx]
            if key in seen:
                removed += 1
                audit.append(
                    AuditRecord(
                        dataset=dataset_name,
                        column="<row>",
                        original_value=record,
                        new_value="<ROW_REMOVED>",
                        cleaning_rule="duplicates_keep_first",
                        row_index=idx,
                    )
                )
                continue
            seen.add(key)
            kept.append(record)
        return kept, removed, audit, warnings

    # ------------------------------------------------------------------
    # KEEP LAST – drop all occurrences except the final one
    # ------------------------------------------------------------------
    if strategy == "keep_last":
        last_index: Dict[str, int] = {}
        for idx, key in enumerate(keys):
            last_index[key] = idx

        kept_last: List[Dict[str, Any]] = []
        for idx, record in enumerate(records):
            key = keys[idx]
            if last_index[key] != idx:
                removed += 1
                audit.append(
                    AuditRecord(
                        dataset=dataset_name,
                        column="<row>",
                        original_value=record,
                        new_value="<ROW_REMOVED>",
                        cleaning_rule="duplicates_keep_last",
                        row_index=idx,
                    )
                )
                continue
            kept_last.append(record)
        return kept_last, removed, audit, warnings

    # ------------------------------------------------------------------
    # DROP ALL – remove every row that appears more than once
    # ------------------------------------------------------------------
    if strategy == "drop_all":
        kept_unique: List[Dict[str, Any]] = []
        for idx, record in enumerate(records):
            key = keys[idx]
            if counts[key] > 1:
                removed += 1
                audit.append(
                    AuditRecord(
                        dataset=dataset_name,
                        column="<row>",
                        original_value=record,
                        new_value="<ROW_REMOVED>",
                        cleaning_rule="duplicates_drop_all",
                        row_index=idx,
                    )
                )
                continue
            kept_unique.append(record)
        return kept_unique, removed, audit, warnings

    # ------------------------------------------------------------------
    # Unknown strategy – return original records with a warning
    # ------------------------------------------------------------------
    warnings.append(
        f"Unsupported duplicate strategy '{strategy}'. No duplicate rows removed."
    )
    return records, 0, audit, warnings
