from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONPATH", str(PROJECT_ROOT))
os.environ.setdefault("IRIS_SERVICE", "hub")

from shared.logger import configure_logging  # noqa: E402
from hub.core.migrations import run_migrations  # noqa: E402


def main() -> int:
    configure_logging("hub")
    run_migrations()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
