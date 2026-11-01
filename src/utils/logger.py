"""中文日志工具。

本模块只负责提供统一的中文日志格式，不触发联网、不下载行情数据。
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO


中文日志级别 = {
    logging.DEBUG: "调试",
    logging.INFO: "信息",
    logging.WARNING: "警告",
    logging.ERROR: "错误",
    logging.CRITICAL: "严重",
}

默认日志格式 = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
默认日期格式 = "%Y-%m-%d %H:%M:%S"


class ChineseLevelFormatter(logging.Formatter):
    """把日志级别显示为中文。"""

    def format(self, record: logging.LogRecord) -> str:
        original_level_name = record.levelname
        record.levelname = 中文日志级别.get(record.levelno, original_level_name)
        try:
            return super().format(record)
        finally:
            record.levelname = original_level_name


def get_logger(
    name: str = "Mstock",
    level: int | str = logging.INFO,
    stream: TextIO | None = None,
) -> logging.Logger:
    """创建或获取中文日志对象。"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(ChineseLevelFormatter(默认日志格式, 默认日期格式))
        logger.addHandler(handler)

    for handler in logger.handlers:
        handler.setLevel(level)

    return logger


def log_start(message: str = "任务开始") -> None:
    """输出中文任务开始日志。"""
    get_logger().info(message)


def log_finish(message: str = "任务完成") -> None:
    """输出中文任务完成日志。"""
    get_logger().info(message)


def log_error(message: str = "任务失败") -> None:
    """输出中文错误日志。"""
    get_logger().error(message)
