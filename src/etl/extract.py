"""Raw-file extraction helpers for GridSense AI ETL."""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.etl.exceptions import ETLFileNotFoundError, ETLParseError


@dataclass(slots=True)
class RawDataset:
    """Parsed raw dataset ready for validation."""

    dataset_name: str
    source_path: Path
    file_format: str
    records: List[Dict[str, Any]]


def discover_raw_files(
    raw_root: Path, dataset_filter: Optional[Iterable[str]] = None
) -> List[Path]:
    """Discover raw files under the ingestion root."""

    if not raw_root.exists():
        return []

    allowed = {item.lower() for item in dataset_filter} if dataset_filter else None
    candidates: List[Path] = []
    for file_path in raw_root.rglob("*"):
        if not file_path.is_file() or file_path.name.endswith(".jsonl"):
            continue
        if file_path.suffix.lower() not in {".json", ".csv", ".xml"}:
            continue
        if allowed and not any(part.lower() in allowed for part in file_path.parts):
            continue
        candidates.append(file_path)
    return sorted(candidates)


def load_raw_dataset(file_path: Path, dataset_name: Optional[str] = None) -> RawDataset:
    """Load a raw dataset from JSON, CSV, or XML."""

    if not file_path.exists():
        raise ETLFileNotFoundError(f"Raw dataset not found: {file_path}")

    file_format = file_path.suffix.lower().lstrip(".")
    name = dataset_name or file_path.stem

    if file_format == "json":
        records = _load_json_records(file_path)
    elif file_format == "csv":
        records = _load_csv_records(file_path)
    elif file_format == "xml":
        records = _load_xml_records(file_path)
    else:
        raise ETLParseError(f"Unsupported file format: {file_format}")

    return RawDataset(
        dataset_name=name,
        source_path=file_path,
        file_format=file_format,
        records=records,
    )


def _load_json_records(file_path: Path) -> List[Dict[str, Any]]:
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ETLParseError(f"Invalid JSON in {file_path}: {exc}") from exc

    return _normalize_json_payload(payload)


def _normalize_json_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item if isinstance(item, dict) else {"value": item} for item in payload]

    if isinstance(payload, dict):
        for key in ("records", "data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [
                    item if isinstance(item, dict) else {"value": item}
                    for item in value
                ]

        if payload and all(isinstance(value, list) for value in payload.values()):
            return _transpose_dict_of_lists(payload)

        return [payload]

    return [{"value": payload}]


def _transpose_dict_of_lists(payload: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    rows = max((len(values) for values in payload.values()), default=0)
    records: List[Dict[str, Any]] = []
    for row_index in range(rows):
        record: Dict[str, Any] = {}
        for column_name, values in payload.items():
            record[column_name] = values[row_index] if row_index < len(values) else None
        records.append(record)
    return records


def _load_csv_records(file_path: Path) -> List[Dict[str, Any]]:
    try:
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ETLParseError(f"Invalid CSV header in {file_path}")
            records = [dict(row) for row in reader]
    except csv.Error as exc:
        raise ETLParseError(f"Invalid CSV in {file_path}: {exc}") from exc

    return records


def _load_xml_records(file_path: Path) -> List[Dict[str, Any]]:
    try:
        root = ElementTree.parse(file_path).getroot()
    except ElementTree.ParseError as exc:
        raise ETLParseError(f"Invalid XML in {file_path}: {exc}") from exc

    records: List[Dict[str, Any]] = []
    for child in list(root):
        record = _xml_element_to_dict(child)
        if record:
            records.append(record)

    if not records:
        records.append(_xml_element_to_dict(root))

    return records


def _xml_element_to_dict(element: ElementTree.Element) -> Dict[str, Any]:
    children = list(element)
    if not children:
        return {element.tag: (element.text.strip() if element.text else "")}

    record: Dict[str, Any] = {}
    for child in children:
        if list(child):
            record[child.tag] = _xml_element_to_dict(child)
        else:
            record[child.tag] = child.text.strip() if child.text else ""
    return record
