"""yfinance 日线行情数据源。"""

from __future__ import annotations

import contextlib
from datetime import date
from io import StringIO
import time

import pandas as pd
import requests
import yfinance as yf

from src.data.providers import 行情下载错误, 校验行情字段


英文转中文字段 = {
    "Open": "开盘价",
    "High": "最高价",
    "Low": "最低价",
    "Close": "收盘价",
    "Adj Close": "复权收盘价",
    "Volume": "成交量",
}


class YFinanceProvider:
    """通过 yfinance 下载日线 OHLCV。"""

    数据源名称 = "yfinance"

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    def download_daily(
        self,
        ticker: str,
        days: int = 300,
        start: date | None = None,
    ) -> pd.DataFrame:
        """下载单个标的的日线行情。"""
        if days <= 0:
            raise 行情下载错误(f"{ticker} 下载失败：交易日数量必须大于0。")

        yahoo_ticker = 转换为雅虎代码(ticker)
        download_kwargs = {
            "interval": "1d",
            "auto_adjust": False,
            "progress": False,
            "threads": False,
            "timeout": self.timeout,
        }
        if start:
            download_kwargs["start"] = start.isoformat()
        else:
            download_kwargs["period"] = 计算下载周期(days)

        captured_output = StringIO()
        try:
            with contextlib.redirect_stdout(captured_output), contextlib.redirect_stderr(captured_output):
                raw = yf.download(yahoo_ticker, **download_kwargs)
        except Exception as exc:
            reason = f"yfinance 请求异常，原因：{exc}"
            return 下载YahooChart日线(ticker, days=days, start=start, timeout=self.timeout, 前置错误=reason)

        if raw is None or raw.empty:
            reason = 翻译_yfinance输出(captured_output.getvalue())
            return 下载YahooChart日线(ticker, days=days, start=start, timeout=self.timeout, 前置错误=reason)

        df = 标准化_yfinance结果(raw, ticker)
        if start is None:
            df = df.tail(days).reset_index(drop=True)
        校验行情字段(df, ticker)
        return df


def 计算下载周期(days: int) -> str:
    """把交易日数量转换为 yfinance 可用的自然日周期。"""
    calendar_days = max(int(days * 1.8), days + 30)
    return f"{calendar_days}d"


def 翻译_yfinance输出(text: str) -> str:
    """把 yfinance 的常见英文失败输出转换为中文。"""
    原始信息 = " ".join(text.split())
    原始补充 = f"原始信息：{原始信息[:300]}" if 原始信息 else "原始信息：空"
    if "Too Many Requests" in text or "Rate limited" in text or "YFRateLimitError" in text:
        return f"Yahoo 返回请求过于频繁，当前被临时限流。{原始补充}"
    if "No data found" in text or "possibly delisted" in text:
        return f"没有返回行情数据，代码可能无效、已退市或数据源暂不可用。{原始补充}"
    return f"yfinance 没有返回行情数据。{原始补充}"


def 转换为雅虎代码(ticker: str) -> str:
    """把本项目代码转换为 Yahoo Finance 代码。"""
    return ticker.strip().upper().replace(".", "-")


def 下载YahooChart日线(
    ticker: str,
    days: int = 300,
    start: date | None = None,
    timeout: int = 30,
    前置错误: str | None = None,
) -> pd.DataFrame:
    """使用 Yahoo Chart 直接接口作为 yfinance 兜底。"""
    yahoo_ticker = 转换为雅虎代码(ticker)
    period2 = int(time.time())
    if start:
        period1 = int(pd.Timestamp(start).timestamp())
    else:
        period1 = period2 - max(int(days * 1.8), days + 30) * 24 * 3600

    try:
        response = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}",
            params={
                "period1": period1,
                "period2": period2,
                "interval": "1d",
                "events": "history",
                "includeAdjustedClose": "true",
            },
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        prefix = f"yfinance前置错误：{前置错误}；" if 前置错误 else ""
        raise 行情下载错误(f"{ticker} 下载失败：{prefix}Yahoo Chart 请求异常，原因：{exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        prefix = f"yfinance前置错误：{前置错误}；" if 前置错误 else ""
        raise 行情下载错误(f"{ticker} 下载失败：{prefix}Yahoo Chart 返回不是有效 JSON。") from exc

    df = 标准化_yahoo_chart结果(payload, ticker, 前置错误=前置错误)
    if start is None:
        df = df.tail(days).reset_index(drop=True)
    校验行情字段(df, ticker)
    return df


def 标准化_yahoo_chart结果(payload: dict, ticker: str, 前置错误: str | None = None) -> pd.DataFrame:
    """把 Yahoo Chart JSON 转换为中文 OHLCV 字段。"""
    prefix = f"yfinance前置错误：{前置错误}；" if 前置错误 else ""
    chart = payload.get("chart", {})
    error = chart.get("error")
    if error:
        raise 行情下载错误(f"{ticker} 下载失败：{prefix}Yahoo Chart 返回错误：{error}")

    results = chart.get("result") or []
    if not results:
        raise 行情下载错误(f"{ticker} 下载失败：{prefix}Yahoo Chart 没有返回行情数据。")

    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adjclose = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")
    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in quote]
    if missing:
        raise 行情下载错误(f"{ticker} 下载失败：Yahoo Chart 字段缺失：{missing}")

    rows = []
    for index, timestamp in enumerate(timestamps):
        row = {
            "日期": pd.to_datetime(timestamp, unit="s").strftime("%Y-%m-%d"),
            "代码": ticker.strip().upper(),
            "开盘价": quote["open"][index],
            "最高价": quote["high"][index],
            "最低价": quote["low"][index],
            "收盘价": quote["close"][index],
            "复权收盘价": adjclose[index] if adjclose and index < len(adjclose) else quote["close"][index],
            "成交量": quote["volume"][index],
            "数据来源": "yahoo_chart",
            "更新时间": pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S"),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["开盘价", "最高价", "最低价", "收盘价", "成交量"])
    if df.empty:
        raise 行情下载错误(f"{ticker} 下载失败：{prefix}Yahoo Chart 返回数据全部缺失。")
    return df.sort_values("日期").reset_index(drop=True)


def 展平_yfinance列(df: pd.DataFrame) -> pd.DataFrame:
    """处理 yfinance 可能返回的多层列。"""
    if not isinstance(df.columns, pd.MultiIndex):
        return df.copy()

    known_columns = set(英文转中文字段)
    if known_columns & set(df.columns.get_level_values(0)):
        flattened = df.copy()
        flattened.columns = df.columns.get_level_values(0)
        return flattened

    if known_columns & set(df.columns.get_level_values(-1)):
        flattened = df.copy()
        flattened.columns = df.columns.get_level_values(-1)
        return flattened

    raise 行情下载错误("yfinance 返回字段格式无法识别。")


def 标准化_yfinance结果(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """把 yfinance 返回结果转换为中文 OHLCV 字段。"""
    df = 展平_yfinance列(raw)
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise 行情下载错误(f"{ticker} 下载失败：yfinance 字段缺失：{missing}")

    if "Adj Close" not in df.columns:
        df["Adj Close"] = df["Close"]

    df = df[list(英文转中文字段)].rename(columns=英文转中文字段)
    df = df.reset_index()

    date_column = "Date" if "Date" in df.columns else df.columns[0]
    df["日期"] = pd.to_datetime(df[date_column]).dt.strftime("%Y-%m-%d")
    df["代码"] = ticker.strip().upper()
    df["数据来源"] = "yfinance"
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
    df = df[output_columns].sort_values("日期").reset_index(drop=True)
    return df
