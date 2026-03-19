"""Logging configuration aligned with application core."""

from loguru import logger


def configure_logger(level: str = "INFO", fmt: str = "json"):
    """Configure Loguru for structured or text logging.

    Parameters
    - level: log level string (e.g., INFO)
    - fmt: 'json' or 'text'
    """
    logger.remove()
    if fmt.lower() == "json":
        logger.add(
            sink=lambda m: print(m, end=""),
            level=level.upper(),
            serialize=True,
            enqueue=True,
        )
    else:
        logger.add(
            sink=lambda m: print(m, end=""),
            level=level.upper(),
            format="{time} | {level} | {message}",
            enqueue=True,
        )
    return logger
