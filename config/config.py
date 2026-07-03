"""Configuration Management Module for GridSense AI.

This module loads environment variables from a .env file and provides a
centralized configuration object with type-safe fields and runtime validations.
"""

import os
from pathlib import Path
import logging
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()


class AppConfig:
    """Central configuration class that parses and validates environment settings."""

    def __init__(self) -> None:
        # ====================================================================
        # System Paths
        # ====================================================================
        self.workspace_root: Path = Path(__file__).resolve().parent.parent
        self.log_level_str: str = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_level: int = getattr(logging, self.log_level_str, logging.INFO)
        self.log_dir: Path = self.workspace_root / os.getenv("LOG_DIR", "logs")
        self.raw_data_dir: Path = self.workspace_root / os.getenv(
            "RAW_DATA_DIR", "data/raw"
        )
        self.processed_data_dir: Path = self.workspace_root / os.getenv(
            "PROCESSED_DATA_DIR", "data/processed"
        )
        self.parquet_data_dir: Path = self.workspace_root / os.getenv(
            "PARQUET_DATA_DIR", "data/parquet"
        )
        self.database_dir: Path = self.workspace_root / os.getenv(
            "DATABASE_DIR", "database"
        )
        self.sqlite_dir: Path = self.database_dir / "sqlite"
        self.duckdb_dir: Path = self.database_dir / "duckdb"
        self.reports_dir: Path = self.workspace_root / os.getenv(
            "REPORTS_DIR", "reports"
        )
        self.docs_dir: Path = self.workspace_root / os.getenv("DOCS_DIR", "docs")

        # ====================================================================
        # API Client Configuration
        # ====================================================================
        try:
            self.api_timeout: float = float(os.getenv("API_TIMEOUT_SEC", "15"))
        except ValueError:
            self.api_timeout = 15.0

        try:
            self.api_max_retries: int = int(os.getenv("API_MAX_RETRIES", "5"))
        except ValueError:
            self.api_max_retries = 5

        try:
            self.api_backoff_factor: float = float(
                os.getenv("API_BACKOFF_FACTOR", "2.0")
            )
        except ValueError:
            self.api_backoff_factor = 2.0

        self.user_agent: str = os.getenv(
            "USER_AGENT", "GridSenseAI-Ingestion/2.1.0 (Contact: local-developer)"
        )

        # ====================================================================
        # API Credentials and Keys
        # ====================================================================
        self.datagov_api_key: str = os.getenv("DATAGOV_API_KEY", "")
        self.waqi_api_token: str = os.getenv("WAQI_API_TOKEN", "")
        self.world_bank_api_enabled: bool = (
            os.getenv("WORLD_BANK_ENABLED", "True").lower() == "true"
        )
        self.open_meteo_enabled: bool = (
            os.getenv("OPEN_METEO_ENABLED", "True").lower() == "true"
        )

        # ====================================================================
        # Operational Settings
        # ====================================================================
        try:
            self.pipeline_max_concurrent: int = int(
                os.getenv("PIPELINE_MAX_CONCURRENT", "5")
            )
        except ValueError:
            self.pipeline_max_concurrent = 5

        try:
            self.pipeline_batch_size: int = int(os.getenv("PIPELINE_BATCH_SIZE", "10"))
        except ValueError:
            self.pipeline_batch_size = 10

        self.enable_compression: bool = (
            os.getenv("ENABLE_COMPRESSION", "True").lower() == "true"
        )
        self.enable_caching: bool = (
            os.getenv("ENABLE_CACHING", "False").lower() == "true"
        )
        self.enable_metadata_lineage: bool = (
            os.getenv("ENABLE_METADATA_LINEAGE", "True").lower() == "true"
        )

        # ====================================================================
        # File Format Settings
        # ====================================================================
        self.default_file_format: str = os.getenv("DEFAULT_FILE_FORMAT", "json").lower()
        self.supplementary_formats: list = [
            f.strip().lower()
            for f in os.getenv("SUPPLEMENTARY_FORMATS", "csv,xml").split(",")
        ]

        # ====================================================================
        # Validation and Initialization
        # ====================================================================
        self._validate_and_initialize()

    def _validate_and_initialize(self) -> None:
        """Validates configuration parameters and ensures necessary directories exist."""
        # Create all necessary directories
        self._create_directory(self.log_dir)
        self._create_directory(self.raw_data_dir)
        self._create_directory(self.processed_data_dir)
        self._create_directory(self.parquet_data_dir)
        self._create_directory(self.sqlite_dir)
        self._create_directory(self.duckdb_dir)
        self._create_directory(self.reports_dir)
        self._create_directory(self.docs_dir)

        # Validate that critical paths are writable
        for path_name, path_obj in [
            ("log_dir", self.log_dir),
            ("raw_data_dir", self.raw_data_dir),
        ]:
            if not os.access(path_obj, os.W_OK):
                raise PermissionError(
                    f"Directory '{path_obj}' ({path_name}) is not writable."
                )

        # Warn if critical API keys are missing (non-fatal for testing/dry-runs)
        if not self.datagov_api_key or "YOUR_DATAGOV" in self.datagov_api_key:
            logging.warning(
                "DATAGOV_API_KEY is not configured. Government data extractions will fail."
            )
        if not self.waqi_api_token or "YOUR_WAQI" in self.waqi_api_token:
            logging.warning(
                "WAQI_API_TOKEN is not configured. Air quality extractions will fail."
            )

        # Validate file format settings
        if self.default_file_format not in ["json", "csv", "xml"]:
            logging.warning(
                f"Invalid DEFAULT_FILE_FORMAT '{self.default_file_format}'. Defaulting to 'json'."
            )
            self.default_file_format = "json"

    @staticmethod
    def _create_directory(path: Path) -> None:
        """Creates a directory with parents if it doesn't exist.

        Args:
            path: Path object to create.
        """
        path.mkdir(parents=True, exist_ok=True)

    def get_log_file_path(self, filename: str = "gridsense.log") -> Path:
        """Returns the absolute path to the central log file.

        Args:
            filename: Name of the log file. Defaults to 'gridsense.log'.

        Returns:
            Path: Absolute path to the log file.
        """
        return self.log_dir / filename

    def get_metadata_log_path(self) -> Path:
        """Returns the path to the metadata log file.

        Returns:
            Path: Absolute path to the metadata log file.
        """
        return self.raw_data_dir / "extraction_metadata.jsonl"

    def get_pipeline_summary_path(self) -> Path:
        """Returns the path to the pipeline summary file.

        Returns:
            Path: Absolute path to the pipeline summary file.
        """
        return self.raw_data_dir / "pipeline_summaries.jsonl"


# Singleton instance of configuration loader
config = AppConfig()
