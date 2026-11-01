from pathlib import Path

import pandas as pd
import pytest

from src.data import hot_universe
from src.data.hot_universe import 合并网上热度池, 网上热度池字段, 生成网上热度池
from src.data.web_hot_sources import HotSourceProvider, 网上热度来源错误


class GoodProvider(HotSourceProvider):
    source_key = "good"
    来源网站 = "测试来源"
    来源页面 = "https://example.test/good"
    来源分类 = "涨幅榜"
    入选原因 = "测试涨幅榜"
    requires_network = False

    def fetch(self):
        return self._finalize(
            [
                {"代码": "nbis", "名称": "Nebius", "最新价格": 10, "当日涨幅": 0.1, "成交量": 100},
                {"代码": "AAPL", "名称": "Apple", "最新价格": 20, "当日涨幅": 0.2, "成交量": 200},
            ]
        )


class BadProvider(HotSourceProvider):
    source_key = "bad"
    来源网站 = "失败来源"
    来源页面 = "https://example.test/bad"
    来源分类 = "成交量榜"
    入选原因 = "测试失败来源"
    requires_network = False

    def fetch(self):
        raise 网上热度来源错误("测试来源失败")


def test_duplicate_symbols_are_merged_with_chinese_fields():
    """多来源重复代码可以合并，输出字段保持全中文。"""
    df = pd.DataFrame(
        [
            {"代码": "NBIS", "名称": "Nebius", "来源网站": "来源A", "来源页面": "A", "来源分类": "涨幅榜", "入选原因": "涨幅", "热度说明": "上涨", "最新价格": 10, "当日涨幅": 0.1, "成交量": 100, "成交额": 1000, "市值": 10000, "更新时间": "2026-06-02 10:00:00"},
            {"代码": "NBIS", "名称": "Nebius", "来源网站": "来源B", "来源页面": "B", "来源分类": "阶段新高", "入选原因": "新高", "热度说明": "突破", "最新价格": 11, "当日涨幅": 0.11, "成交量": 300, "成交额": 3300, "市值": 10000, "更新时间": "2026-06-02 10:01:00"},
        ]
    )

    merged = 合并网上热度池(df, metadata=pd.DataFrame({"代码": ["NBIS"], "名称": ["Nebius"], "是否ETF": ["否"]}))

    assert list(merged.columns) == 网上热度池字段
    assert len(merged) == 1
    assert merged.loc[0, "来源网站"] == "来源A；来源B"
    assert merged.loc[0, "是否涨幅榜"] == "是"
    assert merged.loc[0, "是否阶段新高"] == "是"
    assert merged.loc[0, "是否ETF"] == "否"


def test_single_source_failure_does_not_fail_whole_pool(tmp_path, monkeypatch):
    """单个来源失败不会导致整个热度池失败。"""
    monkeypatch.setattr(hot_universe, "创建热度来源", lambda source_keys, config, cache_dir: [GoodProvider(config, cache_dir), BadProvider(config, cache_dir)])
    stock_pool = tmp_path / "股票池.csv"
    pd.DataFrame({"代码": ["NBIS", "AAPL"], "名称": ["Nebius", "Apple"], "是否ETF": ["否", "否"]}).to_csv(stock_pool, index=False, encoding="utf-8-sig")

    result = 生成网上热度池(
        source_keys=["good", "bad"],
        output_path=tmp_path / "网上热度池.csv",
        report_path=tmp_path / "报告.md",
        failure_path=tmp_path / "失败.csv",
        stock_pool_path=stock_pool,
        cache_dir=tmp_path,
        limit=10,
        no_network=True,
    )

    assert len(result.数据) == 2
    assert result.来源成功数量 == 1
    assert result.来源失败数量 == 1
    assert result.输出路径.exists()
    assert result.报告路径.exists()
    failures = pd.read_csv(result.失败清单路径, encoding="utf-8-sig")
    assert failures.loc[0, "失败原因"] == "测试来源失败"


def test_invalid_limit_raises_chinese_error(tmp_path):
    """非法 limit 输出中文错误。"""
    with pytest.raises(ValueError, match="--limit 必须大于0"):
        生成网上热度池(
            source_keys=[],
            output_path=tmp_path / "池.csv",
            report_path=tmp_path / "报告.md",
            failure_path=tmp_path / "失败.csv",
            limit=0,
        )
