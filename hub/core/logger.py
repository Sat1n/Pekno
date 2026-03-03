import logging
import sys
import os

class ColorFormatter(logging.Formatter):
    """自定义颜色格式化器"""
    grey = "\x1b[38;20m"
    blue = "\x1b[34;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    # 格式：时间 - [名称] - 等级 - 消息
    format_str = "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: blue + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)

def setup_logger(name: str):
    logger = logging.getLogger(name)
    level = os.getenv("LOG_LEVEL", "DEBUG").upper() # 默认先开 DEBUG 方便看效果
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter())

    if not logger.handlers:
        logger.addHandler(handler)
    return logger

# 预定义两个主要的 Logger
hub_log = setup_logger("Iris-Hub")
worker_log = setup_logger("Iris-Worker")