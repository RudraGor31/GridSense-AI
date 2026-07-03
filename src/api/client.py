"""Base HTTP Client Module for GridSense AI.

This module implements a reusable API client with thread-safe Request ID generation,
exponential backoff with jitter, error handling, and structured response metadata.
"""

import time
import random
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError
from config.config import config
from src.utils.logging_util import logger

# Thread-safe global counter for request sequence tracking
_counter_lock = threading.Lock()
_request_counter = 0


def generate_request_id() -> str:
    """Generates a unique, traceable Request ID.

    Format: GS-YYYYMMDD-XXXXXX (e.g., GS-20260703-000001)

    Returns:
        str: The generated Request ID.
    """
    global _request_counter
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    with _counter_lock:
        _request_counter += 1
        sequence_num = f"{_request_counter:06d}"
    return f"GS-{date_str}-{sequence_num}"


@dataclass
class ApiResponse:
    """Class encapsulating HTTP response content and execution metadata."""

    request_id: str
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    content_type: str = ""
    response_size: int = 0
    execution_time_ms: float = 0.0
    server_date: str = ""
    etag: Optional[str] = None
    cache_control: Optional[str] = None
    text: str = ""
    success: bool = False
    error_message: Optional[str] = None


class BaseApiClient:
    """Base client wrapping requests.Session with advanced reliability policies."""

    def __init__(
        self,
        base_url: str = "",
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or config.api_timeout
        self.max_retries = max_retries or config.api_max_retries
        self.backoff_factor = backoff_factor or config.api_backoff_factor

        # Configure a persistent HTTP session
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "GridSenseAI-Ingestion/2.1.0 (Contact: local-developer)",
                "Accept": "application/json, text/csv, application/xml",
            }
        )

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
    ) -> ApiResponse:
        """Sends an HTTP request with retry logic and metadata tracking.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: URL path relative to the base URL (or absolute URL).
            params: Query string parameters.
            headers: Specific request headers to apply.
            data: Raw data body.
            json: JSON payload.

        Returns:
            ApiResponse: Container including text payload and metrics.
        """
        request_id = generate_request_id()
        url = (
            endpoint
            if endpoint.startswith(("http://", "https://"))
            else f"{self.base_url}/{endpoint.lstrip('/')}"
        )

        # Merge optional headers
        req_headers = headers or {}

        attempt = 0
        response_obj: Optional[requests.Response] = None
        error_msg: Optional[str] = None
        start_time = time.perf_counter()

        while attempt < self.max_retries:
            attempt += 1
            error_msg = None
            logger.info(
                f"[{request_id}] Ingesting: {method} {url} | Attempt {attempt}/{self.max_retries}"
            )

            try:
                # Execute request
                response_obj = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    headers=req_headers,
                    data=data,
                    json=json,
                    timeout=self.timeout,
                )

                # Check status code classification
                status_code = response_obj.status_code

                # Success path (HTTP 200s, 300s)
                if 200 <= status_code < 400:
                    execution_time = (time.perf_counter() - start_time) * 1000.0
                    return self._build_api_response(
                        request_id=request_id,
                        response=response_obj,
                        execution_time_ms=execution_time,
                        success=True,
                    )

                # Trigger retry logic for specific server errors (500s) or rate limiting (429)
                if status_code == 429 or 500 <= status_code < 600:
                    error_msg = f"HTTP {status_code} received from server."
                    logger.warning(
                        f"[{request_id}] Retryable server issue on attempt {attempt}: {error_msg}"
                    )
                else:
                    # Non-retryable failure (e.g. 400 Bad Request, 401 Unauthorized, 404 Not Found)
                    error_msg = f"HTTP {status_code} client error."
                    logger.error(
                        f"[{request_id}] Non-retryable request error: {error_msg}"
                    )
                    break

            except Timeout as te:
                error_msg = f"Network timeout after {self.timeout}s."
                logger.warning(
                    f"[{request_id}] Connection timeout on attempt {attempt}: {te}"
                )
            except ConnectionError as ce:
                error_msg = "Connection refused or network interface down."
                logger.warning(
                    f"[{request_id}] Connection error on attempt {attempt}: {ce}"
                )
            except RequestException as re:
                error_msg = f"Requests request failure: {re}"
                logger.warning(
                    f"[{request_id}] General request exception on attempt {attempt}: {re}"
                )
            except Exception as ex:
                error_msg = f"Unknown execution error: {ex}"
                logger.error(f"[{request_id}] Unhandled Exception: {ex}")
                break

            # Calculate backoff delay with jitter
            # Formula: Base * 2^attempt + random(0, 1)
            if attempt < self.max_retries:
                sleep_sec = (self.backoff_factor * (2**attempt)) + random.uniform(
                    0.0, 1.0
                )
                logger.info(f"[{request_id}] Sleeping {sleep_sec:.2f}s before retry...")
                time.sleep(sleep_sec)

        # Execution reached limit without success
        execution_time = (time.perf_counter() - start_time) * 1000.0
        logger.error(
            f"[{request_id}] Pipeline request failed. Attempts: {attempt}. Error: {error_msg}"
        )

        return self._build_failed_api_response(
            request_id=request_id,
            status_code=response_obj.status_code if response_obj is not None else 0,
            error_message=error_msg or "Max retries exhausted.",
            execution_time_ms=execution_time,
            response=response_obj,
        )

    def _build_api_response(
        self,
        request_id: str,
        response: requests.Response,
        execution_time_ms: float,
        success: bool,
    ) -> ApiResponse:
        """Parses headers and payload to build an ApiResponse object."""
        headers_dict = dict(response.headers)
        content_type = headers_dict.get("Content-Type", "")
        response_size = len(response.content)
        server_date = headers_dict.get("Date", "")
        etag = headers_dict.get("ETag")
        cache_control = headers_dict.get("Cache-Control")

        return ApiResponse(
            request_id=request_id,
            status_code=response.status_code,
            headers=headers_dict,
            content_type=content_type,
            response_size=response_size,
            execution_time_ms=execution_time_ms,
            server_date=server_date,
            etag=etag,
            cache_control=cache_control,
            text=response.text,
            success=success,
        )

    def _build_failed_api_response(
        self,
        request_id: str,
        status_code: int,
        error_message: str,
        execution_time_ms: float,
        response: Optional[requests.Response],
    ) -> ApiResponse:
        """Constructs an ApiResponse for failed requests."""
        if response is not None:
            return self._build_api_response(
                request_id=request_id,
                response=response,
                execution_time_ms=execution_time_ms,
                success=False,
            )

        return ApiResponse(
            request_id=request_id,
            status_code=status_code,
            success=False,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
        )
