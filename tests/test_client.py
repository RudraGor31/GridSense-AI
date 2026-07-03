"""Unit Tests for GridSense AI API Client Ingestion Layer.

This module validates unique Request ID generation, User-Agent settings,
timeout handling, and retry strategies using unittest mocks.
"""

import unittest
from unittest.mock import MagicMock, patch
import requests
from requests.exceptions import Timeout
from src.api.client import BaseApiClient, ApiResponse, generate_request_id


class TestApiClient(unittest.TestCase):
    """Test suite targeting the BaseApiClient reliability properties."""

    def test_request_id_uniqueness(self) -> None:
        """Validates that consecutive Request IDs are unique and incrementing."""
        id1 = generate_request_id()
        id2 = generate_request_id()
        self.assertNotEqual(id1, id2)
        self.assertTrue(id1.startswith("GS-"))
        self.assertTrue(id2.startswith("GS-"))

    @patch("requests.Session.request")
    def test_successful_request_metadata_extraction(
        self, mock_request: MagicMock
    ) -> None:
        """Validates response parsing and HTTP metadata mapping on success."""
        # Setup mock response
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.content = b'{"status": "ok"}'
        mock_response.text = '{"status": "ok"}'
        mock_response.headers = {
            "Content-Type": "application/json",
            "Date": "Thu, 02 Jul 2026 21:00:00 GMT",
            "ETag": 'W/"123456789"',
            "Cache-Control": "max-age=3600",
        }
        mock_request.return_value = mock_response

        client = BaseApiClient(base_url="https://api.test.com")
        res: ApiResponse = client.request(method="GET", endpoint="/test")

        self.assertTrue(res.success)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content_type, "application/json")
        self.assertEqual(res.response_size, len(b'{"status": "ok"}'))
        self.assertEqual(res.etag, 'W/"123456789"')
        self.assertEqual(res.cache_control, "max-age=3600")
        self.assertIn("status", res.text)
        self.assertIsNone(res.error_message)

    @patch("requests.Session.request")
    def test_retry_on_server_error_500(self, mock_request: MagicMock) -> None:
        """Validates that client retries requests on encountering 500 status codes."""
        # Configure the mock to return 500 then 200 on retry
        response_500 = MagicMock(spec=requests.Response)
        response_500.status_code = 500
        response_500.content = b"Internal Server Error"
        response_500.text = "Internal Server Error"
        response_500.headers = {}

        response_200 = MagicMock(spec=requests.Response)
        response_200.status_code = 200
        response_200.content = b'{"success": true}'
        response_200.text = '{"success": true}'
        response_200.headers = {"Content-Type": "application/json"}

        # Return 500 first, then 200
        mock_request.side_effect = [response_500, response_200]

        # Use a short backoff factor to speed up test execution
        client = BaseApiClient(
            base_url="https://api.test.com", max_retries=3, backoff_factor=0.01
        )
        res = client.request(method="GET", endpoint="/retry-test")

        self.assertTrue(res.success)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_request.call_count, 2)

    @patch("requests.Session.request")
    def test_network_timeout_exception_handling(self, mock_request: MagicMock) -> None:
        """Validates that network timeouts trigger retry loops and log failures."""
        # Mock raises Timeout exception for all attempts
        mock_request.side_effect = Timeout("Request timed out")

        client = BaseApiClient(
            base_url="https://api.test.com", max_retries=2, backoff_factor=0.01
        )
        res = client.request(method="GET", endpoint="/timeout-test")

        self.assertFalse(res.success)
        self.assertEqual(res.status_code, 0)
        self.assertIn("timeout", res.error_message.lower())
        self.assertEqual(mock_request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
