import logging
import sys
from typing import Any

import structlog

from app.core.config import settings


def setup_logging() -> None:
    """Configure structured logging for the application."""

    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        # JSON logs for production (easy to ingest in Datadog, Loki, etc.)
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Human-readable logs for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging so third-party libs (uvicorn, sqlalchemy) use same format
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    for noisy_logger in ("uvicorn.access",):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    return structlog.get_logger(name)
