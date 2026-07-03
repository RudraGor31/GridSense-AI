"""Tests for the Phase 4.1 ETL foundation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from src.etl.extract import discover_raw_files, load_raw_dataset
from src.etl.pipeline import ETLPipeline
from src.etl.quality import calculate_quality_score
from src.etl.schema_validator import ColumnRule, SchemaDefinition, SchemaValidator
from src.etl.validate import ValidationService


def test_load_raw_json_dataset() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "sample.json"
        file_path.write_text(
            json.dumps([{"timestamp": "2026-07-03T00:00:00Z", "value": 1}]),
            encoding="utf-8",
        )

        dataset = load_raw_dataset(file_path, dataset_name="sample")

        assert dataset.dataset_name == "sample"
        assert dataset.file_format == "json"
        assert len(dataset.records) == 1


def test_schema_validator_detects_invalid_rows() -> None:
    schema = SchemaDefinition(
        name="sample",
        columns={
            "timestamp": ColumnRule(
                name="timestamp", data_type="timestamp", required=True
            ),
            "latitude": ColumnRule(
                name="latitude",
                data_type="number",
                required=True,
                minimum=-90.0,
                maximum=90.0,
            ),
            "longitude": ColumnRule(
                name="longitude",
                data_type="number",
                required=True,
                minimum=-180.0,
                maximum=180.0,
            ),
            "count": ColumnRule(
                name="count", data_type="integer", required=True, allow_negative=False
            ),
        },
        allow_extra_columns=False,
        unique_key=("timestamp", "latitude", "longitude"),
    )
    validator = SchemaValidator()
    result = validator.validate(
        [
            {
                "timestamp": "2026-07-03T00:00:00Z",
                "latitude": 12.5,
                "longitude": 77.5,
                "count": 3,
            },
            {
                "timestamp": "bad",
                "latitude": 95,
                "longitude": 200,
                "count": -1,
                "extra": "x",
            },
        ],
        schema,
    )

    assert result.rows_checked == 2
    assert result.valid_rows == 1
    assert result.invalid_rows == 1
    assert not result.is_valid
    assert result.unexpected_columns == ["extra"]
    assert any("timestamp" in error for error in result.errors)


def test_validation_service_builds_report() -> None:
    schema = SchemaDefinition(
        name="sample",
        columns={
            "timestamp": ColumnRule(
                name="timestamp", data_type="timestamp", required=True
            ),
            "value": ColumnRule(
                name="value", data_type="number", required=True, allow_negative=False
            ),
        },
    )
    service = ValidationService()
    outcome = service.validate(
        dataset_name="sample",
        records=[{"timestamp": "2026-07-03T00:00:00Z", "value": 1.5}],
        source_path=Path("/tmp/sample.json"),
        file_format="json",
        schema=schema,
        processing_time_seconds=0.1,
    )

    assert outcome.report is not None
    assert outcome.report.status == "PASS"
    assert outcome.report.rows_valid == 1
    assert outcome.validated_records == [
        {"timestamp": "2026-07-03T00:00:00Z", "value": 1.5}
    ]


def test_quality_score_bounds() -> None:
    assert calculate_quality_score(0, 0, 0, 0) == 0.0
    assert 0.0 <= calculate_quality_score(10, 10, 0, 0) <= 100.0


def test_discover_raw_files_filters_extensions() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "cea" / "2026" / "07" / "03").mkdir(parents=True)
        json_file = root / "cea" / "2026" / "07" / "03" / "sample.json"
        csv_file = root / "cea" / "2026" / "07" / "03" / "sample.csv"
        txt_file = root / "cea" / "2026" / "07" / "03" / "sample.txt"
        json_file.write_text("[]", encoding="utf-8")
        csv_file.write_text("timestamp,value\n2026-07-03T00:00:00Z,1", encoding="utf-8")
        txt_file.write_text("ignore", encoding="utf-8")

        files = discover_raw_files(root)

        assert json_file in files
        assert csv_file in files
        assert txt_file not in files


def test_etl_pipeline_creates_quality_report_and_staging_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        raw_root = root / "data" / "raw"
        processed_root = root / "data" / "processed"
        reports_root = root / "reports"
        raw_dataset_dir = raw_root / "cea" / "2026" / "07" / "03"
        raw_dataset_dir.mkdir(parents=True)
        sample_file = raw_dataset_dir / "cea.json"
        sample_file.write_text(
            json.dumps(
                [
                    {
                        "timestamp": "2026-07-03T00:00:00Z",
                        "state": "Delhi",
                        "demand_mw": 1200.5,
                        "supply_mw": 1198.0,
                    },
                    {
                        "timestamp": "2026-07-03T01:00:00Z",
                        "state": "Delhi",
                        "demand_mw": 1210.0,
                        "supply_mw": 1202.0,
                    },
                ]
            ),
            encoding="utf-8",
        )

        pipeline = ETLPipeline(
            raw_root=raw_root, processed_root=processed_root, reports_root=reports_root
        )
        result = pipeline.run(dataset_filter=["cea"])

        assert result.datasets_processed == 1
        assert result.datasets_validated == 1
        assert result.datasets_failed == 0
        assert result.quality_reports_written == 1
        assert result.staging_files_written == 1
        assert result.dataset_results[0]["status"] == "PASS"
        assert (reports_root / "data_quality").exists()
        assert (processed_root / "staging" / "cea").exists()
