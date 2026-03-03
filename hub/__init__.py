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

__all__ = [
    "core",
    "UniversalItem",
    "ItemIntent",
    "ItemStatus",
]