from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.data.cache import (
    代码转缓存文件名,
    导入手动CSV,
    批量更新日线缓存,
    读取失败代码,
    统计缓存文件数量,
    选择下载代码,
)
from src.data.providers import 自动行情数据源, 行情下载错误
from src.data.yfinance_provider import 标准化_yahoo_chart结果, 标准化_yfinance结果, 翻译_yfinance输出, 转换为雅虎代码


class FakeProvider:
    数据源名称 = "测试数据源"

    def __init__(self, fail_tickers=None):
        self.fail_tickers = set(fail_tickers or [])
        self.calls = []

    def download_daily(self, ticker: str, days: int = 300, start: date | None = None) -> pd.DataFrame:
        self.calls.append((ticker, days, start))
        if ticker in self.fail_tickers:
            raise 行情下载错误(f"{ticker} 测试下载失败。")

        日期 = pd.date_range("2026-01-01", periods=min(days, 3), freq="D")
        if start:
            日期 = pd.date_range(start, periods=2, freq="D")

        return pd.DataFrame(
            {
                "日期": [item.strftime("%Y-%m-%d") for item in 日期],
                "代码": ticker,
                "开盘价": [10.0 + index for index in range(len(日期))],
                "最高价": [11.0 + index for index in range(len(日期))],
                "最低价": [9.0 + index for index in range(len(日期))],
                "收盘价": [10.5 + index for index in range(len(日期))],
                "复权收盘价": [10.5 + index for index in range(len(日期))],
                "成交量": [1000 + index for index in range(len(日期))],
                "数据来源": "测试数据源",
                "更新时间": "2026-06-01 10:00:00",
            }
        )


class FlakyProvider(FakeProvider):
    """第一次失败，第二次成功的测试数据源。"""

    def __init__(self):
        super().__init__()
        self.count = 0

    def download_daily(self, ticker: str, days: int = 300, start: date | None = None) -> pd.DataFrame:
        self.count += 1
        if self.count == 1:
            raise 行情下载错误(f"{ticker} 临时限流：Too Many Requests")
        return super().download_daily(ticker, days=days, start=start)


def test_select_tickers_includes_benchmarks_and_limit(tmp_path):
    """检查选择代码时包含 QQQ 和 SPY，并支持 limit。"""
    stock_pool_path = tmp_path / "美股股票池.csv"
    pd.DataFrame(
        {
            "代码": ["AAPL", "MSFT", "NVDA"],
            "名称": ["苹果", "微软", "英伟达"],
            "市场": ["NASDAQ", "NASDAQ", "NASDAQ"],
            "是否ETF": ["否", "否", "否"],
        }
    ).to_csv(stock_pool_path, index=False, encoding="utf-8-sig")

    tickers = 选择下载代码(stock_pool_path, limit=2)

    assert tickers == ["QQQ", "SPY", "AAPL", "MSFT"]


def test_select_explicit_tickers_are_deduplicated_and_include_benchmarks(tmp_path):
    """检查指定代码时自动补充基准并去重。"""
    stock_pool_path = tmp_path / "美股股票池.csv"
    pd.DataFrame(
        {
            "代码": ["AAPL"],
            "名称": ["苹果"],
            "市场": ["NASDAQ"],
            "是否ETF": ["否"],
        }
    ).to_csv(stock_pool_path, index=False, encoding="utf-8-sig")

    tickers = 选择下载代码(stock_pool_path, tickers="AAPL,QQQ,MSFT,AAPL")

    assert tickers == ["QQQ", "SPY", "AAPL", "MSFT"]


def test_cache_filename_is_safe():
    """检查缓存文件名转换。"""
    assert 代码转缓存文件名("BRK.A") == "BRK.A.csv"
    assert 代码转缓存文件名("abc/us") == "ABC-US.csv"


def test_batch_update_writes_cache_and_failure_list(tmp_path):
    """检查批量更新会写缓存和失败清单。"""
    provider = FakeProvider(fail_tickers={"BAD"})
    failure_path = tmp_path / "output" / "下载失败清单.csv"

    result = 批量更新日线缓存(
        provider=provider,
        tickers=["AAPL", "BAD"],
        cache_dir=tmp_path / "cache",
        days=3,
        force=True,
        failure_path=failure_path,
    )

    assert result.成功数量 == 1
    assert result.失败数量 == 1
    assert (tmp_path / "cache" / "daily" / "AAPL.csv").exists()
    assert failure_path.exists()
    assert 统计缓存文件数量(tmp_path / "cache") == 1

    failures = pd.read_csv(failure_path)
    assert failures["代码"].tolist() == ["BAD"]
    assert "行情下载失败" in failures["失败原因"].iloc[0]


def test_retry_failed_codes_are_loaded_from_failure_list(tmp_path):
    """检查失败清单可以用于重试下载。"""
    failure_path = tmp_path / "下载失败清单.csv"
    pd.DataFrame(
        {
            "代码": ["AAPL", "QQQ", "AAPL"],
            "失败原因": ["失败", "失败", "失败"],
            "更新时间": ["2026-06-01", "2026-06-01", "2026-06-01"],
        }
    ).to_csv(failure_path, index=False, encoding="utf-8-sig")

    tickers = 读取失败代码(failure_path)

    assert tickers == ["QQQ", "SPY", "AAPL"]


def test_batch_update_retries_before_failure(tmp_path):
    """检查批量更新会按重试次数再次尝试。"""
    provider = FlakyProvider()

    result = 批量更新日线缓存(
        provider=provider,
        tickers=["AAPL"],
        cache_dir=tmp_path / "cache",
        days=3,
        force=True,
        failure_path=tmp_path / "output" / "下载失败清单.csv",
        max_retries=1,
        sleep_min=0,
        sleep_max=0,
    )

    assert result.成功数量 == 1
    assert provider.count == 2


def test_incremental_update_uses_start_date(tmp_path):
    """检查已有缓存时使用增量开始日期。"""
    provider = FakeProvider()

    first = 批量更新日线缓存(
        provider=provider,
        tickers=["AAPL"],
        cache_dir=tmp_path / "cache",
        days=3,
        force=True,
        failure_path=tmp_path / "output" / "下载失败清单.csv",
    )
    second = 批量更新日线缓存(
        provider=provider,
        tickers=["AAPL"],
        cache_dir=tmp_path / "cache",
        days=5,
        force=False,
        failure_path=tmp_path / "output" / "下载失败清单.csv",
    )

    assert first.成功数量 == 1
    assert second.成功数量 == 1
    assert provider.calls[-1][2] == date(2026, 1, 4)


def test_yfinance_result_standardizes_to_chinese_columns():
    """检查 yfinance 原始结果可转换为中文字段。"""
    raw = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.5],
            "Adj Close": [10.4],
            "Volume": [1000],
        },
        index=pd.to_datetime(["2026-01-01"]),
    )

    df = 标准化_yfinance结果(raw, "AAPL")

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
    assert df["代码"].iloc[0] == "AAPL"


def test_yfinance_missing_columns_raise_chinese_error():
    """检查 yfinance 缺失必要字段时抛出中文错误。"""
    raw = pd.DataFrame({"Open": [10.0]}, index=pd.to_datetime(["2026-01-01"]))

    with pytest.raises(行情下载错误, match="字段缺失"):
        标准化_yfinance结果(raw, "AAPL")


def test_yahoo_ticker_conversion():
    """检查 Yahoo Finance 代码转换。"""
    assert 转换为雅虎代码("brk.a") == "BRK-A"


def test_yfinance_error_translation_is_chinese():
    """检查 yfinance 英文错误会转换成中文说明。"""
    reason = 翻译_yfinance输出("YFRateLimitError('Too Many Requests. Rate limited.')")

    assert reason.startswith("Yahoo 返回请求过于频繁，当前被临时限流。")
    assert "原始信息" in reason


def test_yahoo_chart_result_standardizes_to_chinese_columns():
    """检查 Yahoo Chart JSON 可转换为中文字段。"""
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1767225600],
                    "indicators": {
                        "quote": [
                            {
                                "open": [10.0],
                                "high": [11.0],
                                "low": [9.0],
                                "close": [10.5],
                                "volume": [1000],
                            }
                        ],
                        "adjclose": [{"adjclose": [10.4]}],
                    },
                }
            ],
            "error": None,
        }
    }

    df = 标准化_yahoo_chart结果(payload, "AAPL")

    assert df["代码"].iloc[0] == "AAPL"
    assert df["数据来源"].iloc[0] == "yahoo_chart"
    assert "复权收盘价" in df.columns


def test_auto_provider_falls_back_to_second_provider():
    """检查自动数据源会在第一个失败后尝试第二个。"""
    bad_provider = FakeProvider(fail_tickers={"AAPL"})
    good_provider = FakeProvider()
    provider = 自动行情数据源([bad_provider, good_provider])

    df = provider.download_daily("AAPL", days=3)

    assert not df.empty
    assert bad_provider.calls[0][0] == "AAPL"
    assert good_provider.calls[0][0] == "AAPL"


def test_manual_csv_import_writes_cache(tmp_path):
    """检查手动 CSV 可以导入日线缓存。"""
    import_path = tmp_path / "AAPL.csv"
    pd.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-02"],
            "Open": [10.0, 11.0],
            "High": [11.0, 12.0],
            "Low": [9.0, 10.0],
            "Close": [10.5, 11.5],
            "Volume": [1000, 2000],
        }
    ).to_csv(import_path, index=False)

    results = 导入手动CSV(import_path, cache_dir=tmp_path / "cache", days=300, ticker="AAPL")

    assert len(results) == 1
    assert results[0].代码 == "AAPL"
    assert (tmp_path / "cache" / "daily" / "AAPL.csv").exists()
