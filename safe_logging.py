from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any


REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "accesstoken",
    "refreshtoken",
    "token",
    "password",
    "terminalkey",
    "rebillid",
    "paymenturl",
    "cardid",
    "pan",
    "data",
    "receipt",
}
_KEY_PATTERN = "|".join(
    sorted(
        {
            "access_token",
            "refresh_token",
            "token",
            "password",
            "terminalkey",
            "terminal_key",
            "rebillid",
            "rebill_id",
            "paymenturl",
            "payment_url",
            "cardid",
            "card_id",
            "pan",
            "data",
            "receipt",
        },
        key=len,
        reverse=True,
    )
)
_ASSIGNMENT = re.compile(
    rf"(?i)(?P<prefix>[\"']?(?:{_KEY_PATTERN})[\"']?\s*[:=]\s*)"
    r"(?P<quote>[\"']?)(?P<value>[^\s,;}&\"']+)(?P=quote)"
)
_LABEL = re.compile(rf"(?i)(?P<prefix>\b(?:{_KEY_PATTERN})\b\s+)(?P<value>[^\s,;}}]+)")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def _normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def mask_identifier(value: Any) -> str:
    text = str(value or "")
    if len(text) <= 8:
        return REDACTED
    return f"{text[:4]}...{text[-4:]}"


def redact_text(value: Any) -> str:
    text = str(value)
    text = _BEARER.sub(f"Bearer {REDACTED}", text)
    text = _JWT.sub(REDACTED, text)
    text = _ASSIGNMENT.sub(
        lambda match: f"{match.group('prefix')}{match.group('quote')}{REDACTED}{match.group('quote')}",
        text,
    )
    return _LABEL.sub(
        lambda match: f"{match.group('prefix')}{REDACTED}",
        text,
    )


def redact(value: Any, *, key: Any = None) -> Any:
    if key is not None and _normalized_key(key) in _SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, Mapping):
        return {
            item_key: redact(item, key=item_key) for item_key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, set):
        return {redact(item) for item in value}
    if isinstance(value, str):
        return redact_text(value)
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.args = redact(record.args)
        record.msg = redact_text(record.getMessage())
        record.args = ()
        return True


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def configure_safe_logging() -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(item, RedactingFilter) for item in handler.filters):
            handler.addFilter(RedactingFilter())
        current = handler.formatter
        handler.setFormatter(
            RedactingFormatter(
                current._fmt if current else None,
                datefmt=current.datefmt if current else None,
                style="%",
            )
        )
