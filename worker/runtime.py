import os


WORKER_EXECUTION_MODE = (
    os.getenv("WORKER_EXECUTION_MODE", os.getenv("EXECUTION_MODE", "cpu")).strip().lower() or "cpu"
)


def is_cuda_execution_mode() -> bool:
    return WORKER_EXECUTION_MODE == "cuda"
