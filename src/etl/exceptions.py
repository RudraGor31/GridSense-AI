"""Custom exceptions for the ETL foundation layer."""


class ETLException(Exception):
    """Base exception for ETL-related failures."""


class ETLFileNotFoundError(ETLException):
    """Raised when a raw input file is missing."""


class ETLParseError(ETLException):
    """Raised when a raw input file cannot be parsed."""


class ETLValidationError(ETLException):
    """Raised when dataset validation fails."""


class ETLStageError(ETLException):
    """Raised when a staging write operation fails."""
