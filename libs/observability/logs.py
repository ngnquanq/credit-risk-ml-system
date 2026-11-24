"""Turn loguru records into the log line defined by contracts/telemetry/log_schema.json."""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
import sys
import traceback
from datetime import timezone
from typing import Any, Callable, Mapping, Optional, TextIO

from loguru import logger

REDACTED = "[REDACTED]"

# Same lists as contracts/telemetry/sensitive_fields.json. A unit test keeps the two equal,
# because inside an image the contracts folder is not there to read.
SENSITIVE_NAMES = frozenset({
    "full_name", "name", "first_name", "last_name",
    "phone", "phone_number", "email",
    "citizen_id", "national_id", "id_number", "passport",
    "date_of_birth", "dob", "address",
    "password", "secret", "token", "access_token", "refresh_token", "id_token",
    "authorization", "cookie", "api_key", "private_key",
})
SENSITIVE_SUFFIXES = ("_enc", "_secret", "_password", "_token")

_LEVELS = {
    "TRACE": "DEBUG", "DEBUG": "DEBUG", "INFO": "INFO", "SUCCESS": "INFO",
    "WARNING": "WARNING", "ERROR": "ERROR", "CRITICAL": "CRITICAL",
}
_BUSINESS_FIELDS = ("application_id", "sk_id_curr", "model_version")
_EVENT = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^[0-9a-f]{16}$")
_NOISY_STDLIB_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn", "gunicorn.error", "gunicorn.access")


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    return k in SENSITIVE_NAMES or k.endswith(SENSITIVE_SUFFIXES)


def _redact(value: Any, key: Optional[str] = None) -> Any:
    if key is not None and _is_sensitive(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_redact(v) for v in value]
    return value


def _active_span_ids() -> Optional[tuple[str, str]]:
    try:
        from opentelemetry import trace
    except ImportError:  # the library works without OpenTelemetry installed
        return None
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


def _build(record: Mapping[str, Any], service: str, component: str) -> dict[str, Any]:
    extra = dict(record["extra"])

    event = str(extra.pop("event", "") or "log")
    fields: dict[str, Any] = {}
    if not _EVENT.match(event):
        fields["event"] = event
        event = "log"

    out: dict[str, Any] = {
        "timestamp": record["time"].astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "level": _LEVELS.get(record["level"].name, "INFO"),
        "service": service,
        "component": component,
        "event": event,
        "message": record["message"],
    }

    trace_id, span_id = extra.pop("trace_id", None), extra.pop("span_id", None)
    if not (isinstance(trace_id, str) and _TRACE_ID.match(trace_id)):
        trace_id, span_id = None, None
        ids = _active_span_ids()
        if ids:
            trace_id, span_id = ids
    if trace_id:
        out["trace_id"] = trace_id
        if isinstance(span_id, str) and _SPAN_ID.match(span_id):
            out["span_id"] = span_id

    for name in _BUSINESS_FIELDS:
        if name in extra:
            out[name] = str(extra.pop(name))

    exc = record["exception"]
    if exc is not None and exc.type is not None:
        err: dict[str, str] = {"type": exc.type.__name__, "message": str(exc.value)}
        err["stack"] = "".join(traceback.format_exception(exc.type, exc.value, exc.traceback))
        out["error"] = err

    fields.update(extra)
    if fields:
        out["fields"] = _redact(fields)
    return out


def _json_sink(stream: TextIO, service: str, component: str) -> Callable[[Any], None]:
    def sink(message: Any) -> None:
        stream.write(json.dumps(_build(message.record, service, component), default=str, ensure_ascii=False) + "\n")
        stream.flush()
    return sink


def _text_sink(stream: TextIO, service: str, component: str) -> Callable[[Any], None]:
    def sink(message: Any) -> None:
        d = _build(message.record, service, component)
        line = f'{d["timestamp"]} {d["level"]:<8} {d["service"]}/{d["component"]} {d["event"]} {d["message"]}'
        extras = {k: v for k, v in d.items() if k not in ("timestamp", "level", "service", "component", "event", "message", "error")}
        if extras:
            line += " " + " ".join(f"{k}={json.dumps(v, default=str, ensure_ascii=False)}" for k, v in extras.items())
        if "error" in d:
            line += "\n" + d["error"]["stack"].rstrip()
        stream.write(line + "\n")
        stream.flush()
    return sink


class _InterceptHandler(logging.Handler):
    """Send the standard library's log records (uvicorn, kafka, mlflow...) through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: Any = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(
    service: str,
    component: str,
    *,
    level: Optional[str] = None,
    fmt: Optional[str] = None,
    stream: Optional[TextIO] = None,
    enqueue: bool = False,
) -> None:
    """Send every log line, loguru's and the standard library's, to ``stream`` in the contract's shape.

    ``level`` defaults to env ``LOG_LEVEL`` (INFO) and ``fmt`` to env ``LOG_FORMAT`` (json). Calling it again replaces the setup.
    """
    level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    fmt = (fmt or os.getenv("LOG_FORMAT") or "json").lower()
    if fmt not in ("json", "text"):
        raise ValueError(f"LOG_FORMAT must be 'json' or 'text', got {fmt!r}")
    try:
        logger.level(level)
    except ValueError:
        raise ValueError(f"Unknown log level {level!r}") from None

    out = stream if stream is not None else sys.stdout
    make_sink = _json_sink if fmt == "json" else _text_sink
    logger.remove()
    logger.add(make_sink(out, service, component), level=level, format="{message}", enqueue=enqueue, backtrace=False, diagnose=False)

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in _NOISY_STDLIB_LOGGERS:
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def log_context(**fields: Any):
    """Add fields (application_id, sk_id_curr, model_version, or any other) to every line logged inside the ``with`` block.

    Works across threads and ``async`` code. Use as ``with log_context(application_id="A-1"):``.
    """
    return logger.contextualize(**fields)
