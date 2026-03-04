"""Top‑level hub package.

Exports the public parts of the subpackages so that consuming
code can do either:

    from hub import core
    from hub import UniversalItem, ItemIntent

or just ``import hub`` and access ``hub.core``.
"""

# expose the subpackage and some of the most commonly used symbols
from . import core
from .core.models import UniversalItem, ItemIntent, ItemStatus
from .core.logger import hub_log, worker_log
from .core.init_db import init_db
from .core.llm.service import LLMManager, LLMService, EmbeddingService
from .core.search import SearchService

__all__ = [
    "core",
    "UniversalItem",
    "ItemIntent",
    "ItemStatus",
    "hub_log",
    "worker_log",
    "init_db",
    "LLMManager",
    "LLMService",
    "EmbeddingService",
    "SearchService"
]