"""Ingestion subpackage for worker component.

Contains the pipeline implementation and the task broker configuration
used by Iris workers when they pull items from plugins and process
them (tagging, summarization, vector storage, etc.).

Typical usage::

    from worker.ingestion import IngestionPipeline, broker

The package exposes the high‑level pipeline class and the broker
instance, making the import paths shorter in application code.
"""

from .pipeline import IngestionPipeline, process_new_item_task

__all__ = [
    "IngestionPipeline",
    "process_new_item_task"
]