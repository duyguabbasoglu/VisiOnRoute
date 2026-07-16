"""Structured logging with secret/PII redaction.

Every process (api, worker, scheduler, cli) calls ``configure_logging`` once.
Output is JSON in production-like environments, colored console locally.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog

# Keys whose values must never reach logs, regardless of nesting.
_SENSITIVE_KEYS = {
    "password",
    "parola",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "authorization",
    "cookie",
    "set-cookie",
    "private_key",
    "card_number",
    "tc_kimlik_no",
}

_BEARER_RE = re.compile(r"(?i)bearer\s+[a-z0-9\-_.~+/=]+")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "[GİZLENDİ]" if str(k).lower() in _SENSITIVE_KEYS else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return _BEARER_RE.sub("bearer [GİZLENDİ]", value)
    return value


def _redaction_processor(
    _logger: structlog.types.WrappedLogger,
    _method: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    return {
        k: "[GİZLENDİ]" if k.lower() in _SENSITIVE_KEYS else _redact(v)
        for k, v in event_dict.items()
    }


def configure_logging(*, json_output: bool, level: int = logging.INFO) -> None:
    renderer: structlog.types.Processor
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redaction_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.types.FilteringBoundLogger:
    logger: structlog.types.FilteringBoundLogger = structlog.get_logger(name)
    return logger
