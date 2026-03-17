"""Top‑level hub package.

Exports the public parts of the subpackages so that consuming
code can do either:

    from hub import core

or just ``import hub`` and access ``hub.core``.
"""

# expose the subpackage and some of the most commonly used symbols
from . import core
from .core.init_db import init_db
from .core.llm.service import LLMManager, LLMService, EmbeddingService
from .core.search import SearchService

__all__ = [
    "core",
    "init_db",
    "LLMManager",
    "LLMService",
    "EmbeddingService",
    "SearchService"
]
