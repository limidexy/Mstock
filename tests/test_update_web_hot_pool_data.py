import argparse
from pathlib import Path

import pandas as pd

from scripts import 更新网上热度池行情 as update_script


def test_hot_pool_download_codes_keep_benchmarks_with_limit(tmp_path):
    """limit 不会截掉 QQQ、SPY。"""
    pool = tmp_path / "网上热度池.csv"
    pd.DataFrame({"代码": ["NBIS", "AAPL", "MSFT"]}).to_csv(pool, index=False, encoding="utf-8-sig")

    codes = update_script.读取热度池代码(pool, limit=1)

    assert codes == ["QQQ", "SPY", "NBIS"]


def test_update_web_hot_pool_supports_missing_only(tmp_path, monkeypatch):
    """更新行情脚本支持 missing-only，并只下载缺失缓存。"""
    pool = tmp_path / "网上热度池.csv"
    pd.DataFrame({"代码": ["NBIS", "AAPL"]}).to_csv(pool, index=False, encoding="utf-8-sig")
    cache_root = tmp_path / "cache"
    (cache_root / "daily").mkdir(parents=True)
    (cache_root / "daily" / "QQQ.csv").write_text("测试", encoding="utf-8")
    (cache_root / "daily" / "AAPL.csv").write_text("测试", encoding="utf-8")
    captured = {}

    class FakeBatchResult:
        成功数量 = 2
        失败数量 = 0
        失败清单路径 = tmp_path / "失败.csv"

    def fake_batch_update(**kwargs):
        captured["tickers"] = kwargs["tickers"]
        kwargs["failure_path"].parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=["代码", "失败原因", "更新时间"]).to_csv(kwargs["failure_path"], index=False, encoding="utf-8-sig")
        return FakeBatchResult()

    monkeypatch.setattr(update_script, "默认缓存根目录", cache_root)
    monkeypatch.setattr(update_script, "创建数据源", lambda provider: object())
    monkeypatch.setattr(update_script, "批量更新日线缓存", fake_batch_update)

    result = update_script.运行更新网上热度池行情(
        argparse.Namespace(
            days=300,
            provider="auto",
            sleep_min=0.0,
            sleep_max=0.0,
            max_retries=0,
            limit=2,
            missing_only=True,
            force=False,
            pool=str(pool),
            failure_output=tmp_path / "失败.csv",
        )
    )

    assert captured["tickers"] == ["SPY", "NBIS"]
    assert result.本轮尝试下载数量 == 2
    assert result.下载失败数量 == 0
