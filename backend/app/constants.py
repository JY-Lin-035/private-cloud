"""
Application constants and enums.

This module contains all magic numbers and constant values used throughout the application.
Following Coding Standards principle: extract magic numbers to named constants.
"""

from enum import IntEnum


class StorageLimits:
    """Storage size limits in bytes."""
    DEFAULT_SIGNAL_FILE_SIZE = 524288000  # 500MB
    DEFAULT_TOTAL_FILE_SIZE = 10737418240  # 10GB


class Identity(IntEnum):
    """User identity types."""
    USER = 0
    ADMIN = 1


class HTTPStatus(IntEnum):
    """HTTP status codes."""
    OK = 200
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    INTERNAL_SERVER_ERROR = 500


class FolderValidation:
    """Folder name validation constants."""
    MIN_LENGTH = 1
    MAX_LENGTH = 30
    PATTERN = r'^[A-Za-z0-9\u4e00-\u9fa5\s\-_\.]+$'


class FileValidation:
    """File path validation constants."""
    MIN_DIR_LENGTH = 1
    MAX_DIR_LENGTH = 255


class AccountDefaults:
    """Default values for account creation."""
    USED_SIZE = 0
    ENABLE = False


class CeleryConfig:
    """Celery worker configuration."""
    WORKER_PREFETCH_MULTIPLIER = 1


class HTTPStatusExtra:
    """Additional HTTP status codes."""
    TOO_MANY_REQUESTS = 429
