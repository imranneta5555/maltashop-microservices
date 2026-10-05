"""Structured JSON logs. Every line carries the correlation ID of the request or event
being handled, so one order can be followed across services."""
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

from . import config

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, timezone.utc)
        entry = {
            "timestamp": timestamp.isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": config.SERVICE_NAME,
            "correlation_id": correlation_id.get(),
            "event": getattr(record, "event", "log"),
            "message": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(config.LOG_LEVEL)
    # Send uvicorn's own messages through the same JSON format.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    logging.getLogger("pika").setLevel(logging.WARNING)


def log_event(logger: logging.Logger, level: int, event: str, message: str, **fields) -> None:
    """Logs one structured line: `event` is a stable, searchable name such as order.placed."""
    logger.log(level, message, extra={"event": event, "fields": fields})
