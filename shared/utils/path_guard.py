"""
Path traversal guard utilities.

Provides a single, reusable function that every file-upload or
file-read endpoint MUST call before persisting or serving a path.
"""
from pathlib import Path

from fastapi import HTTPException


def safe_resolve_path(base_dir: Path, filename: str) -> Path:
    """Resolve *filename* within *base_dir* and guarantee it stays inside.

    Raises ``HTTPException(400)`` when the resolved path escapes.
    """
    # Strip any leading directory components and null bytes
    sanitized = Path(filename).name.replace("\x00", "")
    if not sanitized:
        raise HTTPException(status_code=400, detail="Invalid filename")

    safe_path = (base_dir / sanitized).resolve()
    if not str(safe_path).startswith(str(base_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")

    return safe_path
