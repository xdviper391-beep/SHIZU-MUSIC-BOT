"""Keeps private values (bot token, Spotify keys) out of logs and console.

Everything that goes through the logging system is scrubbed, including traceback text,
so even an exception raised inside discord.py / aiohttp can't print your token.
"""
from __future__ import annotations

import logging
from typing import Iterable, List

from utils import config

REDACTED = "[redacted]"


def _secret_values() -> List[str]:
    values: List[str] = [
        config.TOKEN,
        config.SPOTIFY_CLIENT_ID,
        config.SPOTIFY_CLIENT_SECRET,
    ]
    # longest first; skip tiny values that would mangle normal log text
    unique = {v for v in values if v and len(v) >= 4}
    return sorted(unique, key=len, reverse=True)


def redact(text: str, secrets: Iterable[str] | None = None) -> str:
    for secret in secrets if secrets is not None else _secret_values():
        text = text.replace(secret, REDACTED)
    return text


class RedactFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        self._secrets = _secret_values()

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        try:
            record.msg = redact(record.getMessage(), self._secrets)
            record.args = ()
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = redact(record.exc_text, self._secrets)
            if record.stack_info:
                record.stack_info = redact(record.stack_info, self._secrets)
        except Exception:
            record.msg = "[log line hidden: could not be scrubbed]"
            record.args = ()
            record.exc_info = record.exc_text = None
        return True


def install_redaction() -> None:
    """Attach the filter to every handler on the root logger (call after logging is set up)."""
    flt = RedactFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(flt)
