"""Bounded, credential-redacting application logging."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from typing import Any

from .config import LoggingSettings, log_dir


_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|token|oauth|cookie|authorization|stream[_ -]?key|session[_ -]?id)"
    r"(\s*[:=]\s*|\s+)([^\s,;&]+)"
)
_AUTH_PATTERN = re.compile(
    r"(?i)\b(authorization\s*:\s*(?:bearer|basic)\s+)([^\s,;]+)"
)


def redact(value: Any) -> str:
    text = str(value)
    text = _AUTH_PATTERN.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)


class CredentialRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:
            rendered = str(record.msg)
        record.msg = redact(rendered)
        record.args = ()
        # Exceptions may include request URIs or headers.  The app logs concise
        # exception types itself, so omit unreviewed exception payloads here.
        if record.exc_info:
            exc_type = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            record.msg = f"{record.msg} ({exc_type})"
            record.exc_info = None
            record.exc_text = None
        return True


def configure_logging(
    settings: LoggingSettings | None = None,
    *,
    directory: str | Path | None = None,
) -> Path:
    settings = settings or LoggingSettings()
    target_dir = Path(directory) if directory is not None else log_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "streamer-console.log"

    root = logging.getLogger("streamer_console")
    root.setLevel(getattr(logging, settings.level.upper(), logging.INFO))
    root.propagate = False
    for existing in list(root.handlers):
        root.removeHandler(existing)
        existing.close()

    handler = RotatingFileHandler(
        target,
        maxBytes=settings.max_bytes,
        backupCount=settings.backup_count,
        encoding="utf-8",
        delay=True,
    )
    handler.setLevel(root.level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(CredentialRedactionFilter())
    root.addHandler(handler)
    return target
