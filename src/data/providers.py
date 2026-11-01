"""行情数据源接口。

本模块定义日线行情下载的统一接口，具体实现由 yfinance 等数据源提供。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd


class 行情下载错误(RuntimeError):
    """行情下载失败时抛出的中文异常。"""


@dataclass(frozen=True)
class 日线下载请求:
    """日线行情下载请求。"""

    代码: str
    交易日数量: int = 300
    开始日期: date | None = None
    强制刷新: bool = False


class 日线行情数据源(Protocol):
    """日线行情数据源协议。"""

    数据源名称: str

    def download_daily(
        self,
        ticker: str,
        days: int = 300,
        start: date | None = None,
    ) -> pd.DataFrame:
        """下载单个标的的日线行情。"""
        ...


class 自动行情数据源:
    """按顺序尝试多个数据源，直到某个数据源返回可用行情。"""

    数据源名称 = "auto"

    def __init__(self, providers: list[日线行情数据源]) -> None:
        if not providers:
            raise ValueError("自动数据源初始化失败：至少需要一个可用数据源。")
        self.providers = providers

    def download_daily(
        self,
        ticker: str,
        days: int = 300,
        start: date | None = None,
    ) -> pd.DataFrame:
        """依次尝试多个数据源下载单个标的的日线行情。"""
        errors: list[str] = []

        for provider in self.providers:
            try:
                return provider.download_daily(ticker=ticker, days=days, start=start)
            except Exception as exc:
                provider_name = getattr(provider, "数据源名称", provider.__class__.__name__)
                errors.append(f"{provider_name}失败：{exc}")

        error_text = "；".join(errors)
        raise 行情下载错误(f"{ticker} 自动数据源全部失败：{error_text}")


def 校验行情字段(df: pd.DataFrame, ticker: str) -> None:
    """校验日线行情是否包含必要中文字段。"""
    required_columns = ["日期", "代码", "开盘价", "最高价", "最低价", "收盘价", "成交量"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise 行情下载错误(f"{ticker} 行情字段缺失：{missing_columns}")

    if df.empty:
        raise 行情下载错误(f"{ticker} 没有可用行情数据。")

    missing_data_rows = df[required_columns].isna().any(axis=1).sum()
    if missing_data_rows:
        raise 行情下载错误(f"{ticker} 存在缺失行情数据，缺失行数：{missing_data_rows}")
