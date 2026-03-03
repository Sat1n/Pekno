"""Core helpers and data structures.

This package contains the schema definitions that back the Iris
framework.  Importing the package will bring the model module and
re‑export the most important symbols so callers can write::

    from hub.core import UniversalItem, ItemIntent

without reaching into ``models`` directly.
"""

from . import models

# re‑export a handful of things from models at the package level
from .models import UniversalItem, ItemIntent, ItemStatus

__all__ = [
    "models",
    "UniversalItem",
    "ItemIntent",
    "ItemStatus",
]