"""Core helpers and data structures.

This package contains the schema definitions that back the Iris
framework and the logger for Iris framework.  Importing the package will bring the model module and
re‑export the most important symbols so callers can write::

    from hub.core import UniversalItem, ItemIntent

without reaching into ``models`` directly.
"""

from . import models

# re‑export a handful of things from models at the package level
from .models import UniversalItem, ItemIntent, ItemStatus
from .logger import hub_log, worker_log
from .init_db import init_db
from .llm.service import LLMManager, LLMService, EmbeddingService

__all__ = [
    "models",
    "UniversalItem",
    "ItemIntent",
    "ItemStatus",
    "hub_log",
    "worker_log",
    "init_db",
    "LLMManager",
    "LLMService",
    "EmbeddingService",
]