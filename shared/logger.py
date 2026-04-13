from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("data/logs")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))


class ColorFormatter(logging.Formatter):
    """Console formatter with basic ANSI colors."""

    grey = "\x1b[38;20m"
    blue = "\x1b[34;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format_str = "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: blue + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset,
    }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno, self.format_str)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)


def _get_log_level() -> int:
    app_env = os.getenv("APP_ENV", "dev").lower()
    default_level = "DEBUG" if app_env == "dev" else "INFO"
    level_name = os.getenv("LOG_LEVEL", default_level).upper()
    return getattr(logging, level_name, logging.INFO)


def detect_service_name() -> str:
    explicit = os.getenv("IRIS_SERVICE", "").strip().lower()
    if explicit in {"hub", "worker", "scheduler"}:
        return explicit

    argv = " ".join(sys.argv).lower()
    if "scheduler" in argv:
        return "scheduler"
    if "taskiq" in argv and "worker" in argv:
        return "worker"
    if "uvicorn" in argv or "hub.main" in argv:
        return "hub"
    return "hub"


def get_log_file_path(service_name: str) -> Path:
    return LOG_DIR / f"{service_name}.log"


def _build_console_handler() -> logging.Handler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter())
    handler._iris_owned = True  # type: ignore[attr-defined]
    return handler


def _build_file_handler(service_name: str) -> logging.Handler:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        get_log_file_path(service_name),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler._iris_owned = True  # type: ignore[attr-defined]
    return handler


def configure_logging(service_name: str | None = None) -> str:
    service = service_name or detect_service_name()
    root = logging.getLogger()
    configured_service = getattr(root, "_iris_service_name", None)
    if configured_service == service:
        return service

    root.setLevel(_get_log_level())
    for handler in list(root.handlers):
        if getattr(handler, "_iris_owned", False):
            root.removeHandler(handler)
            handler.close()

    root.addHandler(_build_console_handler())
    root.addHandler(_build_file_handler(service))
    root._iris_service_name = service  # type: ignore[attr-defined]
    return service


configure_logging()

hub_log = logging.getLogger("Iris-Hub")
worker_log = logging.getLogger("Iris-Worker")
scheduler_log = logging.getLogger("Iris-Scheduler")
