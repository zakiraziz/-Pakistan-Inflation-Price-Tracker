"""
log.py
------
Structured (JSON-lines) logging, replacing ad-hoc print() so logs can be
shipped to a log aggregator in production.

Set LOG_LEVEL=DEBUG for verbose output; JSON_LINES=0 for human-readable text.
"""
from __future__ import annotations

import json
import logging
import os
import sys

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str = "app") -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger(name)
    if _CONFIGURED:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    if os.environ.get("JSON_LINES", "1") not in ("0", "false", "False"):
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    _CONFIGURED = True
    return logger