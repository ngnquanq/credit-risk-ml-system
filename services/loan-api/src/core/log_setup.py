"""loan-api's one call to the shared logging library: service name, plus the settings' fallback for level and format."""

import os

from core.config import settings
from observability import configure_logging


def setup_logging(component: str) -> None:
    """``LOG_LEVEL`` and ``LOG_FORMAT`` (the telemetry contract) win; ``APP_LOG_LEVEL`` and ``APP_LOG_FORMAT`` still work."""
    configure_logging(
        service="loan-api",
        component=component,
        level=os.getenv("LOG_LEVEL") or settings.log_level,
        fmt=os.getenv("LOG_FORMAT") or settings.log_format,
    )
