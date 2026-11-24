"""Shared logging for every service. Follows contracts/telemetry/.

    from observability import configure_logging, log_context

    configure_logging(service="loan-api", component="api")      # once, at start-up
    with log_context(application_id="A-123"):                   # optional business context
        logger.info("Application accepted", event="application.accepted")

The code keeps using ``from loguru import logger``. This package only sets where the lines go and what they look like.
It must not import any service: services import it, never the other way round.
"""

from observability.logs import (
    SENSITIVE_NAMES,
    SENSITIVE_SUFFIXES,
    configure_logging,
    log_context,
)

__all__ = ["configure_logging", "log_context", "SENSITIVE_NAMES", "SENSITIVE_SUFFIXES"]
