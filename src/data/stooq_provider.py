"""Stooq 日线行情备用数据源。"""

from __future__ import annotations

from datetime import date
from io import StringIO

import pandas as pd
import requests

from src.data.providers import 行情下载错误, 校验行情字段


STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"

STOOQ字段映射 = {
    "Date": "日期",
    "Open": "开盘价",
    "High": "最高价",
    "Low": "最低价",
    "Close": "收盘价",
    "Volume": "成交量",
}


class StooqProvider:
    """通过 Stooq 下载美股日线 OHLCV。"""

    数据源名称 = "stooq"

    def __init__(self, timeout: int = 30, api_key: str | None = None) -> None:
        self.timeout = timeout
        self.api_key = api_key

    def download_daily(
        self,
        ticker: str,
        days: int = 300,
        start: date | None = None,
    ) -> pd.DataFrame:
        """下载单个标的的日线行情。"""
        if days <= 0:
            raise 行情下载错误(f"{ticker} 下载失败：交易日数量必须大于0。")

        stooq_symbol = 转换为Stooq代码(ticker)
        params = {"s": stooq_symbol, "i": "d"}
        if self.api_key:
            params["apikey"] = self.api_key

        try:
            response = requests.get(
                STOOQ_DAILY_URL,
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": "Mstock/1.0"},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise 行情下载错误(f"{ticker} 下载失败：Stooq 请求异常，原因：{exc}") from exc

        df = 解析Stooq日线CSV(response.text, ticker)
        if start:
            df = df[pd.to_datetime(df["日期"]).dt.date >= start].reset_index(drop=True)
        if df.empty:
            raise 行情下载错误(f"{ticker} 下载失败：Stooq 没有返回行情数据。原始信息：{response.text[:300]}")

        df = df.tail(days).reset_index(drop=True)
        校验行情字段(df, ticker)
        return df


def 转换为Stooq代码(ticker: str) -> str:
    """把美股代码转换为 Stooq 格式，例如 AAPL -> aapl.us。"""
    normalized = ticker.strip().lower().replace("-", ".")
    if normalized.endswith(".us"):
        return normalized
    return f"{normalized}.us"


def 解析Stooq日线CSV(text: str, ticker: str) -> pd.DataFrame:
    """解析 Stooq CSV 为项目中文字段。"""
    if not text.strip():
        raise 行情下载错误(f"{ticker} 下载失败：Stooq 返回内容为空。")
    if "Get your apikey" in text or "get_apikey" in text:
        raise 行情下载错误(f"{ticker} 下载失败：Stooq 当前需要 API key。原始信息：{text[:300]}")
    if text.strip().lower().startswith("no data"):
        raise 行情下载错误(f"{ticker} 下载失败：Stooq 没有返回行情数据。原始信息：{text[:300]}")

    csv_text = 提取StooqCSV文本(text, ticker)
    try:
        raw = pd.read_csv(StringIO(csv_text))
    except Exception as exc:
        raise 行情下载错误(f"{ticker} 下载失败：Stooq CSV 解析失败，原因：{exc}") from exc

    missing = [column for column in STOOQ字段映射 if column not in raw.columns]
    if missing:
        raise 行情下载错误(f"{ticker} 下载失败：Stooq 字段缺失：{missing}。原始信息：{text[:300]}")

    df = raw[list(STOOQ字段映射)].rename(columns=STOOQ字段映射)
    df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
    df["代码"] = ticker.strip().upper()
    df["复权收盘价"] = df["收盘价"]
    df["数据来源"] = "stooq"
    df["更新时间"] = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S")

    output_columns = [
        "日期",
        "代码",
        "开盘价",
        "最高价",
        "最低价",
        "收盘价",
        "复权收盘价",
        "成交量",
        "数据来源",
        "更新时间",
    ]
    return df[output_columns].sort_values("日期").reset_index(drop=True)


def 提取StooqCSV文本(text: str, ticker: str) -> str:
    """从 Stooq 响应中提取 CSV 表头开始的内容。"""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("Date,Open,High,Low,Close,Volume"):
            return "\n".join(lines[index:])
    raise 行情下载错误(f"{ticker} 下载失败：Stooq 返回内容不是日线CSV。原始信息：{text[:300]}")
