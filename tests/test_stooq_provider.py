from datetime import date

import pandas as pd
import pytest
import requests

from src.data.providers import 行情下载错误
from src.data.stooq_provider import StooqProvider, 解析Stooq日线CSV, 转换为Stooq代码


STOOQ样例 = """Date,Open,High,Low,Close,Volume
2026-01-01,10.0,11.0,9.5,10.5,1000
2026-01-02,10.5,12.0,10.2,11.8,1500
2026-01-03,11.8,12.5,11.2,12.1,1800
"""


class FakeResponse:
    """模拟 requests 响应。"""

    def __init__(self, text: str, status_error: Exception | None = None):
        self.text = text
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error


def test_stooq_symbol_conversion():
    """检查美股代码转换为 Stooq 格式。"""
    assert 转换为Stooq代码("AAPL") == "aapl.us"
    assert 转换为Stooq代码("MSFT") == "msft.us"
    assert 转换为Stooq代码("QQQ") == "qqq.us"
    assert 转换为Stooq代码("SPY") == "spy.us"


def test_stooq_csv_parses_to_chinese_columns():
    """检查 Stooq CSV 解析为中文字段。"""
    df = 解析Stooq日线CSV(STOOQ样例, "AAPL")

    assert df.columns.tolist() == [
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
    assert df["代码"].tolist() == ["AAPL", "AAPL", "AAPL"]
    assert df["数据来源"].iloc[0] == "stooq"


def test_stooq_provider_download_uses_timeout_and_filters_start(monkeypatch):
    """检查 Stooq provider 使用超时参数，并支持开始日期过滤。"""
    calls = []

    def fake_get(url, params, timeout, headers):
        calls.append({"url": url, "params": params, "timeout": timeout, "headers": headers})
        return FakeResponse(STOOQ样例)

    monkeypatch.setattr("requests.get", fake_get)
    provider = StooqProvider(timeout=9)

    df = provider.download_daily("AAPL", days=300, start=date(2026, 1, 2))

    assert calls[0]["params"] == {"s": "aapl.us", "i": "d"}
    assert calls[0]["timeout"] == 9
    assert df["日期"].tolist() == ["2026-01-02", "2026-01-03"]


def test_stooq_provider_passes_api_key(monkeypatch):
    """检查 Stooq provider 可以传入 API key。"""
    calls = []

    def fake_get(url, params, timeout, headers):
        calls.append(params)
        return FakeResponse(STOOQ样例)

    monkeypatch.setattr("requests.get", fake_get)
    provider = StooqProvider(timeout=9, api_key="测试KEY")

    provider.download_daily("MSFT")

    assert calls[0]["apikey"] == "测试KEY"


def test_stooq_provider_request_error_is_chinese(monkeypatch):
    """检查 Stooq 请求失败时抛出中文异常。"""

    def fake_get(*args, **kwargs):
        raise requests.RequestException("connection failed")

    monkeypatch.setattr("requests.get", fake_get)
    provider = StooqProvider(timeout=1)

    with pytest.raises(行情下载错误, match="Stooq 请求异常"):
        provider.download_daily("AAPL")


def test_stooq_no_data_is_chinese_error():
    """检查 Stooq 无数据时抛出中文异常。"""
    with pytest.raises(行情下载错误, match="Stooq 没有返回行情数据"):
        解析Stooq日线CSV("No data", "BAD")


def test_stooq_api_key_required_message_is_chinese_error():
    """检查 Stooq 要求 API key 时抛出中文异常。"""
    with pytest.raises(行情下载错误, match="需要 API key"):
        解析Stooq日线CSV("Get your apikey:\nOpen https://stooq.com/q/d/?s=qqq.us&get_apikey", "QQQ")
