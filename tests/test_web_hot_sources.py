import json

import pandas as pd

from src.data.web_hot_sources import (
    EastMoneyHotProvider,
    HotSourceConfig,
    TonghuashunHotProvider,
    YahooGainersProvider,
    默认来源列表,
    网上热度来源字段,
    标准化代码,
    解析数字,
    解析百分比,
)


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def request(self, method, url, headers=None, timeout=None, json=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "timeout": timeout, "json": json})
        return FakeResponse(json_module.dumps(self.payload))


class FakeTextSession:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def request(self, method, url, headers=None, timeout=None, json=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "timeout": timeout, "json": json})
        return FakeResponse(self.text)


json_module = json


def test_yahoo_provider_output_has_unified_chinese_fields(tmp_path):
    """Yahoo provider 输出统一中文字段。"""
    payload = {
        "finance": {
            "result": [
                {
                    "quotes": [
                        {
                            "symbol": "NBIS",
                            "shortName": "Nebius",
                            "regularMarketPrice": 264.51,
                            "regularMarketChangePercent": 14.46,
                            "regularMarketVolume": 23568945,
                            "marketCap": 50000000000,
                        }
                    ]
                }
            ]
        }
    }
    session = FakeSession(payload)
    provider = YahooGainersProvider(
        HotSourceConfig(timeout=7, sleep_min=0, sleep_max=0, max_retries=0, raw_cache_dir=tmp_path, session=session)
    )

    df = provider.fetch()

    assert list(df.columns) == 网上热度来源字段
    assert df.loc[0, "代码"] == "NBIS"
    assert df.loc[0, "来源分类"] == "涨幅榜"
    assert df.loc[0, "当日涨幅"] == 0.1446
    assert session.calls[0]["timeout"] == 7
    assert "User-Agent" in session.calls[0]["headers"]


def test_number_and_percent_parsing():
    """数字和百分比解析支持常见网页格式。"""
    assert 解析数字("$1.5B") == 1_500_000_000
    assert 解析数字("2,300") == 2300
    assert 解析数字("7644.66万") == 76_446_600
    assert 解析数字("3.2亿") == 320_000_000
    assert 解析百分比("14.46%") == 0.1446
    assert 解析百分比(0.12) == 0.12
    assert pd.isna(解析数字("—"))


def test_symbol_normalization_filters_obvious_non_us_suffixes():
    """代码标准化过滤明显非美股后缀，并兼容美股类别股写法。"""
    assert 标准化代码("ASML.AS") == ""
    assert 标准化代码("D05.SI") == ""
    assert 标准化代码("ANTH.PVT") == ""
    assert 标准化代码("BRK.B") == "BRK-B"


def test_default_sources_include_domestic_public_sources():
    """默认来源包含国内公开热度源。"""
    assert "eastmoney_hot" in 默认来源列表
    assert "tonghuashun_hot" in 默认来源列表


def test_eastmoney_provider_parses_public_us_rankings(tmp_path):
    """东方财富公开美股榜可以解析为统一中文字段。"""
    payload = {
        "data": {
            "diff": [
                {"f12": "NBIS", "f14": "Nebius", "f2": 264.51, "f3": 14.46, "f5": 1000, "f6": 264510, "f20": 1000000}
            ]
        }
    }
    provider = EastMoneyHotProvider(
        HotSourceConfig(timeout=7, sleep_min=0, sleep_max=0, max_retries=0, raw_cache_dir=tmp_path, session=FakeSession(payload))
    )

    df = provider.fetch()

    assert list(df.columns) == 网上热度来源字段
    assert set(df["来源分类"]) == {"涨幅榜", "成交量榜", "成交额榜"}
    assert set(df["代码"]) == {"NBIS"}
    assert (df["来源网站"] == "东方财富").all()


def test_tonghuashun_provider_parses_public_html_table(tmp_path):
    """同花顺公开美股页面表格可以解析为统一中文字段。"""
    html = """
    <table>
      <tr><th>序号</th><th>代码</th><th>名称</th><th>现价</th><th>涨跌幅(%)</th><th>成交量</th></tr>
      <tr><td>1</td><td>NBIS</td><td>Nebius</td><td>264.51</td><td>14.46</td><td>100万</td></tr>
    </table>
    """
    provider = TonghuashunHotProvider(
        HotSourceConfig(timeout=7, sleep_min=0, sleep_max=0, max_retries=0, raw_cache_dir=tmp_path, session=FakeTextSession(html))
    )

    df = provider.fetch()

    assert list(df.columns) == 网上热度来源字段
    assert df.loc[0, "代码"] == "NBIS"
    assert df.loc[0, "来源网站"] == "同花顺"
    assert df.loc[0, "成交量"] == 1_000_000
