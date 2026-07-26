"""Dataset cleaning engine – Phase 4.2 orchestration layer.

The :class:`CleaningEngine` orchestrates config-driven cleaning of validated
staging datasets.  It reads every ``*.jsonl`` file under
``data/processed/staging/<dataset>/``, applies a deterministic sequence of
cleaning transformations, and writes:

- Clean dataset JSON  → ``data/processed/clean/<dataset>/<stem>.json``
- Cleaning summary    → ``reports/cleaning/<dataset>_<timestamp>.json``
- Audit trail (JSONL) → ``reports/cleaning/audit/<dataset>/<timestamp>.jsonl``

Cleaning pipeline order
-----------------------
1. Column name standardisation (snake_case, text normalisation).
2. Missing value handling (per-column configurable strategy).
3. Duplicate row handling (keep_first / keep_last / drop_all).
4. Data type coercion and categorical value mapping.
5. Unit standardisation (temperature, wind speed, pressure, etc.).
6. Coordinate validation (latitude / longitude range checks).
7. Outlier flagging (IQR / Z-score; never automatic removal).
8. Clean dataset write, summary generation, audit log write.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.config import config
from src.etl.audit import (
    AuditRecord,
    CleaningSummary,
    compute_cleaning_score,
    write_audit_log,
    write_cleaning_summary,
)
from src.etl.cleaning_rules import (
    CleaningConfig,
    DatasetCleaningConfig,
    default_cleaning_config,
    get_dataset_config,
)
from src.etl.duplicates import handle_duplicates
from src.etl.missing_values import handle_missing_values
from src.etl.normalization import flag_outliers, standardize_units, validate_coordinates
from src.etl.standardize import standardize_columns, standardize_types_and_categories
from src.utils.helpers import save_file_atomically
from src.utils.logging_util import logger


@dataclass(slots=True)
class CleaningResult:
    """Result for one dataset file cleaning operation.

    Attributes
    ----------
    dataset_name:
        Name of the dataset that was cleaned.
    rows_before:
        Row count in the staging file before cleaning.
    rows_after:
        Row count in the clean output (may be less if rows were dropped).
    clean_file_path:
        Absolute path to the written clean JSON file.
    summary_path:
        Absolute path to the cleaning summary JSON file.
    audit_path:
        Absolute path to the JSONL audit log file.
    cleaning_score:
        0-100 composite quality score.
    warnings:
        Non-fatal issues encountered during this cleaning run.
    errors:
        Fatal or near-fatal issues encountered during this cleaning run.
    """

    dataset_name: str
    rows_before: int
    rows_after: int
    clean_file_path: str
    summary_path: str
    audit_path: str
    cleaning_score: float
    warnings: List[str]
    errors: List[str]


class CleaningEngine:
    """Orchestrate config-driven cleaning across all staged datasets.

    Parameters
    ----------
    processed_root:
        Root of the processed data tree (defaults to ``config.processed_data_dir``).
        Expects sub-directories ``staging/`` and will create ``clean/``.
    reports_root:
        Root for report output (defaults to ``config.reports_dir``).
    cleaning_config:
        Top-level cleaning configuration.  Defaults to
        :func:`~src.etl.cleaning_rules.default_cleaning_config`.

    Examples
    --------
    >>> engine = CleaningEngine()
    >>> results = engine.run(dataset_filter=["weather"])
    >>> for r in results:
    ...     print(r.dataset_name, r.cleaning_score)
    """

    def __init__(
        self,
        processed_root: Optional[Path] = None,
        reports_root: Optional[Path] = None,
        cleaning_config: Optional[CleaningConfig] = None,
    ) -> None:
        self.processed_root = processed_root or Path(config.processed_data_dir)
        self.reports_root = reports_root or Path(config.reports_dir)
        self.cleaning_config = cleaning_config or default_cleaning_config()

        self.staging_root = self.processed_root / "staging"
        self.clean_root = self.processed_root / "clean"
        self.clean_root.mkdir(parents=True, exist_ok=True)
        self.reports_root.mkdir(parents=True, exist_ok=True)

    def run(self, dataset_filter: Optional[List[str]] = None) -> List[CleaningResult]:
        """Run the cleaning pipeline across all staged datasets.

        Parameters
        ----------
        dataset_filter:
            If provided, only datasets whose name (lower-case) is in this list
            are processed.  Useful for partial runs or testing.

        Returns
        -------
        list[CleaningResult]
            One result per ``*.jsonl`` file processed.
        """
        results: List[CleaningResult] = []
        for dataset_dir in sorted(self.staging_root.glob("*")):
            if not dataset_dir.is_dir():
                continue

            dataset_name = dataset_dir.name.lower()
            if dataset_filter and dataset_name not in {
                item.lower() for item in dataset_filter
            }:
                continue

            for file_path in sorted(dataset_dir.glob("*.jsonl")):
                result = self._clean_file(dataset_name, file_path)
                results.append(result)

        return results

    def _clean_file(self, dataset_name: str, file_path: Path) -> CleaningResult:
        """Execute the full cleaning pipeline on a single staging JSONL file.

        Parameters
        ----------
        dataset_name:
            Name of the dataset (used for config lookup, logging, and paths).
        file_path:
            Path to the ``.jsonl`` staging file.

        Returns
        -------
        CleaningResult
        """
        start = time.perf_counter()
        errors: List[str] = []
        warnings: List[str] = []
        audit_records: List[AuditRecord] = []

        records = self._read_jsonl_records(file_path)
        rows_before = len(records)

        dataset_config = get_dataset_config(self.cleaning_config, dataset_name)
        if dataset_config is None:
            dataset_config = DatasetCleaningConfig(dataset_name=dataset_name)
            warnings.append(
                f"No cleaning config found for dataset '{dataset_name}'."
                " Applying minimal standardisation only."
            )

        # ------------------------------------------------------------------
        # Step 1 – Column name standardisation
        # ------------------------------------------------------------------
        records, renamed_count, column_audit = standardize_columns(
            records, dataset_name
        )
        audit_records.extend(column_audit)

        # ------------------------------------------------------------------
        # Step 2 – Missing value handling
        # ------------------------------------------------------------------
        records, missing_fixed, missing_audit, missing_warnings = handle_missing_values(
            records,
            dataset_name,
            dataset_config.missing_values,
        )
        audit_records.extend(missing_audit)
        warnings.extend(missing_warnings)

        # ------------------------------------------------------------------
        # Step 3 – Duplicate handling
        # ------------------------------------------------------------------
        records, duplicates_removed, duplicate_audit, duplicate_warnings = (
            handle_duplicates(
                records,
                dataset_name,
                dataset_config.duplicates,
            )
        )
        audit_records.extend(duplicate_audit)
        warnings.extend(duplicate_warnings)

        # ------------------------------------------------------------------
        # Step 4 – Type coercion and categorical mapping
        # ------------------------------------------------------------------
        (
            records,
            dtypes_corrected,
            dtype_audit,
            timezone_metadata,
            dtype_warnings,
        ) = standardize_types_and_categories(
            records,
            dataset_name,
            {
                column: rule.target_type
                for column, rule in dataset_config.dtypes.items()
            },
            dataset_config.categoricals,
            {
                column: {
                    "timezone": rule.timezone,
                    "output_format": rule.output_format,
                }
                for column, rule in dataset_config.timestamps.items()
            },
        )
        audit_records.extend(dtype_audit)
        warnings.extend(dtype_warnings)

        # ------------------------------------------------------------------
        # Step 5 – Unit standardisation
        # ------------------------------------------------------------------
        records, unit_audit, unit_warnings = standardize_units(
            records,
            dataset_name,
            dataset_config.units,
        )
        audit_records.extend(unit_audit)
        warnings.extend(unit_warnings)

        # ------------------------------------------------------------------
        # Step 6 – Coordinate validation
        # ------------------------------------------------------------------
        warnings.extend(validate_coordinates(records))

        # ------------------------------------------------------------------
        # Step 7 – Outlier flagging
        # ------------------------------------------------------------------
        outliers_flagged, outlier_warnings = flag_outliers(
            records, dataset_config.outlier_columns
        )
        warnings.extend(outlier_warnings)

        rows_after = len(records)
        execution_time = round(time.perf_counter() - start, 4)

        # ------------------------------------------------------------------
        # Step 8 – Summary, audit log, and clean dataset output
        # ------------------------------------------------------------------
        summary = CleaningSummary(
            dataset=dataset_name,
            rows_before=rows_before,
            rows_after=rows_after,
            missing_values_fixed=missing_fixed,
            duplicates_removed=duplicates_removed,
            columns_renamed=renamed_count,
            data_types_corrected=dtypes_corrected,
            outliers_flagged=outliers_flagged,
            execution_time_seconds=execution_time,
            warnings=warnings,
            errors=errors,
        )
        summary.cleaning_score = compute_cleaning_score(summary)

        clean_file = self._write_clean_dataset(
            dataset_name, file_path.stem, records, timezone_metadata
        )
        audit_path = write_audit_log(audit_records, self.reports_root, dataset_name)
        summary_path = write_cleaning_summary(summary, self.reports_root)

        logger.info(
            "Cleaning completed | dataset=%s | rows_before=%s | rows_after=%s"
            " | score=%s | time=%.4fs | warnings=%s",
            dataset_name,
            rows_before,
            rows_after,
            summary.cleaning_score,
            execution_time,
            len(warnings),
        )

        return CleaningResult(
            dataset_name=dataset_name,
            rows_before=rows_before,
            rows_after=rows_after,
            clean_file_path=str(clean_file),
            summary_path=str(summary_path),
            audit_path=str(audit_path),
            cleaning_score=summary.cleaning_score,
            warnings=warnings,
            errors=errors,
        )

    @staticmethod
    def _read_jsonl_records(file_path: Path) -> List[Dict[str, Any]]:
        """Read a JSONL file and return a list of record dicts.

        Empty lines are silently skipped.

        Parameters
        ----------
        file_path:
            Absolute path to the ``.jsonl`` file.

        Returns
        -------
        list[dict]
        """
        records: List[Dict[str, Any]] = []
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        return records

    def _write_clean_dataset(
        self,
        dataset_name: str,
        source_stem: str,
        records: List[Dict[str, Any]],
        timezone_metadata: Dict[str, str],
    ) -> Path:
        """Write the clean dataset to ``data/processed/clean/<dataset>/``.

        The output is a JSON envelope containing dataset metadata alongside
        the cleaned rows, written atomically.

        Parameters
        ----------
        dataset_name:
            Dataset identifier.
        source_stem:
            Stem of the source staging filename (used for the output filename).
        records:
            Cleaned rows.
        timezone_metadata:
            ``{column: tz_label}`` map produced during timestamp standardisation.

        Returns
        -------
        Path
            Path to the written clean JSON file.
        """
        dataset_dir = self.clean_root / dataset_name
        dataset_dir.mkdir(parents=True, exist_ok=True)
        output_path = dataset_dir / f"{source_stem}.json"
        payload = {
            "dataset": dataset_name,
            "cleaned_at": time.time(),
            "timezone_metadata": timezone_metadata,
            "rows": records,
        }
        save_file_atomically(
            json.dumps(payload, indent=2, ensure_ascii=False), output_path
        )
        return output_path
