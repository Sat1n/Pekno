import os
from pathlib import Path
from typing import Callable

from shared.logger import hub_log


def _secret_dir() -> Path:
    raw_dir = os.getenv("IRIS_SECRET_DIR", "./data/secrets")
    return Path(raw_dir).expanduser().resolve()


def _write_secret_once(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return

    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value)


def load_or_create_secret(
    *,
    env_key: str,
    filename: str,
    generator: Callable[[], str],
    announce_label: str,
) -> str:
    env_value = os.getenv(env_key)
    if env_value:
        hub_log.info("Using %s from environment variable %s.", announce_label, env_key)
        return env_value.strip()

    secret_path = _secret_dir() / filename
    if secret_path.exists():
        hub_log.info("Reusing persisted %s from %s.", announce_label, secret_path)
        return secret_path.read_text(encoding="utf-8").strip()

    value = generator()
    _write_secret_once(secret_path, value)

    final_value = secret_path.read_text(encoding="utf-8").strip()
    hub_log.info("Generated %s and persisted it to %s.", announce_label, secret_path)
    return final_value
