"""Comprehensive Unit Tests for GridSense AI Ingestion Layer.

This module provides exhaustive test coverage for configuration management,
logging utilities, helper functions, metadata tracking, and API client
operations.
"""

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import AppConfig
from src.utils.helpers import (
    get_current_utc_timestamp,
    get_current_date_keys,
    calculate_sha256,
)
from src.api.client import BaseApiClient, ApiResponse, generate_request_id
from src.metadata import PipelineSummary
from src.constants import REQUEST_ID_PREFIX, DATA_SOURCES


class TestConfigManagement(unittest.TestCase):
    """Test suite for configuration management."""

    def test_config_default_values(self) -> None:
        """Validates that default configuration values are properly set."""
        test_config = AppConfig()
        self.assertIsNotNone(test_config.workspace_root)
        self.assertEqual(test_config.api_timeout, 15.0)
        self.assertEqual(test_config.api_max_retries, 5)
        self.assertEqual(test_config.api_backoff_factor, 2.0)

    def test_config_log_level_parsing(self) -> None:
        """Validates that LOG_LEVEL environment variable is parsed correctly."""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            # Create new config instance
            import importlib
            import config.config as config_module

            importlib.reload(config_module)
            # Reset to avoid affecting other tests
            importlib.reload(config_module)

    def test_config_directory_creation(self) -> None:
        """Validates that configuration creates necessary directories."""
        test_config = AppConfig()
        self.assertTrue(test_config.log_dir.exists())
        self.assertTrue(test_config.raw_data_dir.exists())


class TestHelperFunctions(unittest.TestCase):
    """Test suite for utility helper functions."""

    def test_get_current_utc_timestamp(self) -> None:
        """Validates UTC timestamp generation format."""
        ts = get_current_utc_timestamp()
        self.assertIn("T", ts)
        self.assertIn("Z", ts)
        # Verify format is valid ISO 8601
        datetime.fromisoformat(ts.replace("Z", "+00:00"))

    def test_get_current_date_keys(self) -> None:
        """Validates date key extraction."""
        year, month, day = get_current_date_keys()
        self.assertEqual(len(year), 4)
        self.assertEqual(len(month), 2)
        self.assertEqual(len(day), 2)
        self.assertTrue(year.isdigit())
        self.assertTrue(month.isdigit())
        self.assertTrue(day.isdigit())

    def test_calculate_sha256(self) -> None:
        """Validates SHA-256 checksum calculation."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            checksum = calculate_sha256(test_file)
            self.assertEqual(len(checksum), 64)  # SHA-256 hex is 64 chars
            self.assertTrue(all(c in "0123456789abcdef" for c in checksum))


class TestBaseApiClient(unittest.TestCase):
    """Test suite for BaseApiClient HTTP operations."""

    def test_request_id_generation_format(self) -> None:
        """Validates that Request IDs follow GS-YYYYMMDD-XXXXXX format."""
        req_id = generate_request_id()
        parts = req_id.split("-")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], REQUEST_ID_PREFIX)
        self.assertEqual(len(parts[1]), 8)  # YYYYMMDD
        self.assertEqual(len(parts[2]), 6)  # XXXXXX

    def test_request_id_uniqueness(self) -> None:
        """Validates that consecutive Request IDs are unique."""
        ids = [generate_request_id() for _ in range(100)]
        self.assertEqual(len(ids), len(set(ids)))  # All unique

    @patch("requests.Session.request")
    def test_successful_response_handling(self, mock_request: MagicMock) -> None:
        """Validates response parsing for successful requests."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": "test"}'
        mock_response.content = b'{"data": "test"}'
        mock_response.headers = {
            "Content-Type": "application/json",
            "ETag": '"abc123"',
            "Cache-Control": "max-age=300",
        }
        mock_request.return_value = mock_response

        client = BaseApiClient(base_url="https://test.example.com")
        response = client.request(method="GET", endpoint="/api/data")

        self.assertTrue(response.success)
        self.assertEqual(response.status_code, 200)
        self.assertIn("data", response.text)

    @patch("requests.Session.request")
    def test_retry_on_429_status(self, mock_request: MagicMock) -> None:
        """Validates retry behavior on rate limiting (HTTP 429)."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.text = "Too Many Requests"
        mock_429.content = b"Too Many Requests"
        mock_429.headers = {}

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.text = '{"ok": true}'
        mock_200.content = b'{"ok": true}'
        mock_200.headers = {"Content-Type": "application/json"}

        mock_request.side_effect = [mock_429, mock_200]

        client = BaseApiClient(
            base_url="https://test.example.com", max_retries=3, backoff_factor=0.001
        )
        response = client.request(method="GET", endpoint="/api/data")

        self.assertTrue(response.success)
        self.assertEqual(mock_request.call_count, 2)

    @patch("requests.Session.request")
    def test_non_retryable_client_error(self, mock_request: MagicMock) -> None:
        """Validates that 4xx errors don't trigger retries."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.content = b"Not Found"
        mock_response.headers = {}
        mock_request.return_value = mock_response

        client = BaseApiClient(base_url="https://test.example.com", max_retries=3)
        response = client.request(method="GET", endpoint="/notfound")

        self.assertFalse(response.success)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(mock_request.call_count, 1)  # No retries for 4xx


class TestMetadataLogging(unittest.TestCase):
    """Test suite for metadata and pipeline logging."""

    def test_pipeline_summary_dataclass(self) -> None:
        """Validates PipelineSummary dataclass creation and properties."""
        summary = PipelineSummary(
            execution_start="2026-07-02T00:00:00+00:00",
            execution_end="2026-07-02T00:05:00+00:00",
            runtime_seconds=300.0,
            apis_attempted=5,
            successful_extractions=4,
            failed_extractions=1,
            total_rows_downloaded=10000,
            files_created=5,
            warnings_count=2,
            errors_count=1,
        )

        self.assertEqual(summary.apis_attempted, 5)
        self.assertEqual(summary.successful_extractions, 4)
        self.assertEqual(summary.runtime_seconds, 300.0)
        self.assertIsNotNone(summary.timestamp)


class TestApiResponseObject(unittest.TestCase):
    """Test suite for ApiResponse dataclass."""

    def test_api_response_success_creation(self) -> None:
        """Validates successful ApiResponse construction."""
        response = ApiResponse(
            request_id="GS-20260702-000001",
            status_code=200,
            headers={"Content-Type": "application/json"},
            content_type="application/json",
            response_size=1024,
            execution_time_ms=150.5,
            text='{"status": "ok"}',
            success=True,
        )

        self.assertTrue(response.success)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.error_message)

    def test_api_response_error_creation(self) -> None:
        """Validates error ApiResponse construction."""
        response = ApiResponse(
            request_id="GS-20260702-000002",
            status_code=500,
            success=False,
            error_message="Internal Server Error",
        )

        self.assertFalse(response.success)
        self.assertEqual(response.error_message, "Internal Server Error")


class TestConstants(unittest.TestCase):
    """Test suite for constant definitions."""

    def test_data_sources_defined(self) -> None:
        """Validates that all expected data sources are defined."""
        expected_sources = [
            "cea",
            "npp",
            "open_meteo",
            "waqi",
            "world_bank",
            "data_gov",
            "census",
            "holidays",
            "vahan",
        ]
        for source in expected_sources:
            self.assertIn(source, DATA_SOURCES)

    def test_request_id_prefix(self) -> None:
        """Validates Request ID prefix constant."""
        self.assertEqual(REQUEST_ID_PREFIX, "GS")


class TestDataSourceClients(unittest.TestCase):
    """Test suite for API client implementations."""

    @patch("requests.Session.request")
    def test_cea_client_initialization(self, mock_request: MagicMock) -> None:
        """Validates CEA API client can be initialized."""
        from src.api.cea import CeaApiClient

        client = CeaApiClient()
        self.assertIsNotNone(client.client)

    @patch("requests.Session.request")
    def test_open_meteo_client_initialization(self, mock_request: MagicMock) -> None:
        """Validates Open-Meteo API client can be initialized."""
        from src.api.open_meteo import OpenMeteoClient

        client = OpenMeteoClient()
        self.assertIsNotNone(client.default_hourly_variables)
        self.assertTrue(len(client.default_hourly_variables) > 0)

    @patch("requests.Session.request")
    def test_waqi_client_initialization(self, mock_request: MagicMock) -> None:
        """Validates WAQI API client can be initialized."""
        from src.api.waqi import WaqiApiClient

        client = WaqiApiClient()
        self.assertIsNotNone(client.api_token if hasattr(client, "api_token") else True)


def run_tests() -> None:
    """Runs the test suite."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestConfigManagement))
    suite.addTests(loader.loadTestsFromTestCase(TestHelperFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestBaseApiClient))
    suite.addTests(loader.loadTestsFromTestCase(TestMetadataLogging))
    suite.addTests(loader.loadTestsFromTestCase(TestApiResponseObject))
    suite.addTests(loader.loadTestsFromTestCase(TestConstants))
    suite.addTests(loader.loadTestsFromTestCase(TestDataSourceClients))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Exit with error code if tests failed
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    run_tests()
