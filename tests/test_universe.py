from pathlib import Path

import pandas as pd
import pytest
import requests

from src.data.universe import (
    股票池字段,
    股票池下载错误,
    解析其他上市清单,
    解析纳斯达克上市清单,
    过滤股票池,
    合并并过滤股票池,
    更新股票池,
)


纳斯达克样例 = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N
ARMU|ARM 2x Daily ETF|G|N|N|100|Y|N
TST|Test Company - Common Stock|S|Y|N|100|N|N
ABCW|ABC Corp - Warrant|S|N|N|100|N|N
ABCR|ABC Corp - Rights|S|N|N|100|N|N
ABCU|ABC Corp - Unit|S|N|N|100|N|N
File Creation Time: 0601202618:00
"""

其他上市样例 = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.A|Berkshire Hathaway Inc. Class A Common Stock|N|BRK.A|N|100|N|BRK.A
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
ZZZT|Nasdaq Test Stock|N|ZZZT|N|100|Y|ZZZT
XYZP|XYZ Preferred Stock|A|XYZP|N|100|N|XYZP
NOTE|ABC Senior Notes due 2030|N|NOTE|N|100|N|NOTE
File Creation Time: 0601202618:00
"""


def test_parse_symbol_directory_to_chinese_columns():
    """检查 Nasdaq Trader 文件能解析为中文字段。"""
    df = 解析纳斯达克上市清单(纳斯达克样例, 更新时间="2026-06-01 18:00:00")

    assert list(df.columns) == 股票池字段
    assert "AAPL" in df["代码"].tolist()
    assert df.loc[df["代码"] == "ARMU", "是否ETF"].iloc[0] == "是"
    assert df.loc[df["代码"] == "TST", "是否测试证券"].iloc[0] == "是"


def test_filter_removes_test_and_non_common_symbols_but_keeps_common_and_etf():
    """检查过滤测试证券、权证、权利、单位和优先股，并保留普通股和 ETF。"""
    nasdaq_df = 解析纳斯达克上市清单(纳斯达克样例, 更新时间="2026-06-01 18:00:00")
    other_df = 解析其他上市清单(其他上市样例, 更新时间="2026-06-01 18:00:00")

    result = 合并并过滤股票池([nasdaq_df, other_df])
    codes = set(result["代码"])

    assert {"AAPL", "ARMU", "BRK.A", "SPY"}.issubset(codes)
    assert "TST" not in codes
    assert "ZZZT" not in codes
    assert "ABCW" not in codes
    assert "ABCR" not in codes
    assert "ABCU" not in codes
    assert "XYZP" not in codes
    assert "NOTE" not in codes


def test_filter_output_is_sorted_and_deduplicated():
    """检查过滤后按代码排序并去重。"""
    df = pd.DataFrame(
        [
            {
                "代码": "MSFT",
                "名称": "Microsoft Corporation - Common Stock",
                "市场": "NASDAQ",
                "是否ETF": "否",
                "是否测试证券": "否",
                "数据来源": "测试",
                "更新时间": "2026-06-01 18:00:00",
            },
            {
                "代码": "AAPL",
                "名称": "Apple Inc. - Common Stock",
                "市场": "NASDAQ",
                "是否ETF": "否",
                "是否测试证券": "否",
                "数据来源": "测试",
                "更新时间": "2026-06-01 18:00:00",
            },
            {
                "代码": "AAPL",
                "名称": "Apple Inc. - Common Stock",
                "市场": "NASDAQ",
                "是否ETF": "否",
                "是否测试证券": "否",
                "数据来源": "测试",
                "更新时间": "2026-06-01 18:00:00",
            },
        ]
    )

    result = 过滤股票池(df)

    assert result["代码"].tolist() == ["AAPL", "MSFT"]


def test_update_universe_uses_timeout_and_writes_files(tmp_path, monkeypatch):
    """检查更新流程使用下载函数，并写出原始文件和处理后 CSV。"""
    calls = []

    def fake_download_text(url: str, timeout: int) -> str:
        calls.append((url, timeout))
        if "nasdaqlisted" in url:
            return 纳斯达克样例
        if "otherlisted" in url:
            return 其他上市样例
        raise 股票池下载错误("测试下载失败：未知地址。")

    monkeypatch.setattr("src.data.universe.下载文本", fake_download_text)

    result = 更新股票池(
        raw_dir=tmp_path / "raw",
        output_path=tmp_path / "processed" / "美股股票池.csv",
        timeout=7,
    )

    assert len(calls) == 2
    assert all(timeout == 7 for _, timeout in calls)
    assert result.输出路径.exists()
    assert result.原始文件路径["nasdaqlisted"].exists()
    assert result.原始文件路径["otherlisted"].exists()
    assert result.ETF数量 == 2
    assert result.普通股票数量 == 2

    saved = pd.read_csv(result.输出路径)
    assert list(saved.columns) == 股票池字段


def test_download_error_message_is_chinese(monkeypatch):
    """检查下载失败时错误提示为中文。"""

    def fake_get(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr("requests.get", fake_get)

    from src.data.universe import 下载文本

    with pytest.raises(股票池下载错误, match="下载 Nasdaq Trader 股票清单失败"):
        下载文本("https://example.invalid/test.txt", timeout=1)
