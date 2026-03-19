import os
from pathlib import Path
from typing import Callable


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
        return env_value.strip()

    secret_path = _secret_dir() / filename
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()

    value = generator()
    _write_secret_once(secret_path, value)

    # 如果并发场景中另一进程更早写入，则以磁盘为准，确保 Hub / Worker 一致。
    final_value = secret_path.read_text(encoding="utf-8").strip()
    print(f"🔐 已自动生成 {announce_label}，并持久化到: {secret_path}")
    return final_value
