from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

from shared.time_utils import get_app_timezone

LOG_DIR = Path("data/logs")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
SERVICE_DISPLAY_NAMES = {
    "hub": "Pekno-Hub",
    "worker": "Pekno-Worker",
    "scheduler": "Pekno-Scheduler",
}

# ---------------------------------------------------------------------------
#  Sensitive-value masking
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Bearer <token>
    (re.compile(r'(Bearer\s+)\S+', re.IGNORECASE), r'\1***'),
    # Authorization: <scheme> <token>
    (re.compile(r'(Authorization["\']?\s*[:=]\s*["\']?)\S+', re.IGNORECASE), r'\1***'),
    # GitHub PAT patterns (ghp_, gho_, ghs_, ghr_, github_pat_)
    (re.compile(r'(ghp_|gho_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]+'), '***'),
    # Pekno PAT tokens
    (re.compile(r'(pekno_pat_)[A-Za-z0-9_-]+'), r'\1***'),
    # OpenAI-style keys  sk-...
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), '***'),
    # Fernet-ish base64 tokens (gAAAAA prefix)
    (re.compile(r'gAAAAA[A-Za-z0-9_/+-]{40,}={0,2}'), '***'),
    # Generic key=value in query-strings or logs
    (re.compile(
        r'((?:token|key|secret|password|cookie|sessdata|credential)'
        r'["\']?\s*[:=]\s*["\']?)([^\s"\',;]{4})[^\s"\',;]*',
        re.IGNORECASE,
    ), r'\1\2***'),
]


def _mask_sensitive(message: str) -> str:
    for pattern, replacement in _SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


class SensitiveFilter(logging.Filter):
    """Redact tokens, keys, and credentials from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _mask_sensitive(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: _mask_sensitive(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _mask_sensitive(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


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

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=get_app_timezone())
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="seconds")

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno, self.format_str)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        formatter.formatTime = self.formatTime  # type: ignore[method-assign]
        return formatter.format(record)


class AppFileFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=get_app_timezone())
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="seconds")


class ServiceNameFilter(logging.Filter):
    def __init__(self, service_name: str):
        super().__init__()
        self.display_name = SERVICE_DISPLAY_NAMES.get(service_name, SERVICE_DISPLAY_NAMES["hub"])

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name in SERVICE_DISPLAY_NAMES.values():
            record.name = self.display_name
        return True


def _get_log_level() -> int:
    app_env = os.getenv("APP_ENV", "dev").lower()
    default_level = "DEBUG" if app_env == "dev" else "INFO"
    level_name = os.getenv("LOG_LEVEL", default_level).upper()
    return getattr(logging, level_name, logging.INFO)


def detect_service_name() -> str:
    explicit = os.getenv("PEKNO_SERVICE", "").strip().lower()
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
    handler._pekno_owned = True  # type: ignore[attr-defined]
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
        AppFileFormatter(
            "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler._pekno_owned = True  # type: ignore[attr-defined]
    return handler


def _configure_named_logger(logger_name: str, handlers: list[logging.Handler], level: int) -> None:
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        if getattr(handler, "_pekno_owned", False):
            logger.removeHandler(handler)
            handler.close()
    for handler in handlers:
        logger.addHandler(handler)


def _logger_level_overrides(service: str, root_level: int) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if service == "scheduler":
        overrides["taskiq"] = max(root_level, logging.INFO)
        overrides["taskiq.cli.scheduler.run"] = max(root_level, logging.INFO)
    return overrides


def configure_logging(service_name: str | None = None) -> str:
    explicit_service = os.getenv("PEKNO_SERVICE", "").strip().lower()
    service = explicit_service if explicit_service in SERVICE_DISPLAY_NAMES else (service_name or detect_service_name())
    root = logging.getLogger()
    configured_service = getattr(root, "_pekno_service_name", None)
    if configured_service == service:
        return service

    root.setLevel(_get_log_level())
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    for logger_obj in list(logging.root.manager.loggerDict.values()):
        if not isinstance(logger_obj, logging.Logger):
            continue
        for handler in list(logger_obj.handlers):
            logger_obj.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    console_handler = _build_console_handler()
    file_handler = _build_file_handler(service)
    owned_handlers = [console_handler, file_handler]
    sensitive_filter = SensitiveFilter()
    for handler in owned_handlers:
        root.addHandler(handler)
    for handler in root.handlers:
        if getattr(handler, "_pekno_owned", False):
            handler.addFilter(ServiceNameFilter(service))
            handler.addFilter(sensitive_filter)
    logger_names = (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "taskiq",
        "taskiq.worker",
        "taskiq.process-manager",
        "taskiq.receiver.receiver",
        "taskiq.cli.scheduler.run",
        "httpx",
        "httpcore",
        "httpcore.connection",
        "httpcore.http11",
        "openai",
        "openai._base_client",
    )
    overrides = _logger_level_overrides(service, root.level)
    for logger_name in logger_names:
        _configure_named_logger(logger_name, owned_handlers, overrides.get(logger_name, root.level))
    root._pekno_service_name = service  # type: ignore[attr-defined]
    return service

hub_log = logging.getLogger("Pekno-Hub")
worker_log = logging.getLogger("Pekno-Worker")
scheduler_log = logging.getLogger("Pekno-Scheduler")
app_log = logging.getLogger(SERVICE_DISPLAY_NAMES.get(detect_service_name(), SERVICE_DISPLAY_NAMES["hub"]))
