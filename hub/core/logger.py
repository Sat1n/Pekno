import logging
import sys

def setup_logger(name: str):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 定义日志格式：时间 - 名称 - 等级 - 消息
    formatter = logging.Formatter(
        fmt="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 输出到标准输出（Docker 会捕获这个流）
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger

# 预定义两个主要的 Logger
hub_log = setup_logger("Iris-Hub")
worker_log = setup_logger("Iris-Worker")