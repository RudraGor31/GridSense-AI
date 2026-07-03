"""Helper utilities for file handling, date operations, and checksum calculation.

This module provides reusable utilities for safe path generation, atomic file operations,
and cryptographic integrity validation.
"""

import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Union
from config.config import config
from src.utils.logging_util import logger


def get_current_utc_timestamp() -> str:
    """Returns the current UTC time formatted in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_current_date_keys() -> tuple[str, str, str]:
    """Returns current Year, Month, and Day as strings (UTC-based)."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")


def generate_raw_storage_path(source_name: str) -> Path:
    """Generates and creates a directory path partitioned by source and date.

    Example path: data/raw/cea/2026/07/03/

    Args:
        source_name: The name of the API source.

    Returns:
        Path: The absolute directory path created on disk.
    """
    year, month, day = get_current_date_keys()
    target_dir = Path(config.raw_data_dir) / source_name / year / month / day
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def calculate_sha256(file_path: Union[str, Path]) -> str:
    """Calculates the SHA-256 hash of a file on disk.

    Args:
        file_path: Absolute path to the file.

    Returns:
        str: Hexadecimal string representing the file checksum.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read file in 64KB blocks
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def save_file_atomically(content: Union[str, bytes], target_path: Path) -> str:
    """Writes data atomically to disk by writing to a tempfile then renaming.

    This prevents partially written files in the event of pipeline crashes.

    Args:
        content: The text or binary content to save.
        target_path: The destination path.

    Returns:
        str: The SHA-256 checksum of the written file.
    """
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    mode = "wb" if isinstance(content, bytes) else "w"
    encoding = None if isinstance(content, bytes) else "utf-8"

    # Write to a temporary file in the same directory to guarantee atomic rename
    with tempfile.NamedTemporaryFile(
        mode, dir=target_dir, delete=False, encoding=encoding
    ) as temp_file:
        temp_file.write(content)
        temp_file_path = Path(temp_file.name)

    try:
        # Atomic rename replacing any existing file
        temp_file_path.replace(target_path)
    except Exception as e:
        # Clean up temp file on failure
        if temp_file_path.exists():
            temp_file_path.unlink()
        logger.error(f"Failed atomic file rename to '{target_path}': {e}")
        raise e

    # Generate checksum of successfully saved file
    checksum = calculate_sha256(target_path)
    logger.debug(
        f"Saved file atomically: {target_path.name} | SHA-256: {checksum[:8]}..."
    )
    return checksum
