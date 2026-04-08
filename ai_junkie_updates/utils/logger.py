"""Structured logging configuration using structlog."""

from __future__ import annotations

import logging
import sys

import structlog

from ai_junkie_updates.settings import settings

_configured = False


def _configure_once() -> None:
    """Set up structlog processors and stdlib bridge exactly once."""
    global _configured
    if _configured:
        return
    _configured = True

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Choose renderer based on log level
    if log_level <= logging.DEBUG:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger, configuring the library on first call."""
    _configure_once()
    return structlog.get_logger(logger_name=name)
