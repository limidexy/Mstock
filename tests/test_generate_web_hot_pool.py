import subprocess
import sys
from pathlib import Path

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]


def _write_daily_cache(path: Path, ticker: str, breakout: bool = True, volume_surge: bool = True):
    dates = pd.date_range("2025-01-01", periods=130, freq="B")
    closes = [100 + i * 0.1 for i in range(130)]
    highs = [value + 1 for value in closes]
    lows = [value - 1 for value in closes]
    volumes = [1000] * 130
    if breakout:
        closes[-1] = max(highs[-121:-1]) + 2
        highs[-1] = closes[-1] + 1
        lows[-1] = closes[-1] - 1
    if volume_surge:
        volumes[-1] = 3000
    df = pd.DataFrame(
        {
            "日期": dates.strftime("%Y-%m-%d"),
            "代码": ticker,
            "开盘价": closes,
            "最高价": highs,
            "最低价": lows,
            "收盘价": closes,
            "复权收盘价": closes,
            "成交量": volumes,
            "数据来源": "测试缓存",
            "更新时间": "2026-06-02 10:00:00",
        }
    )
    df.to_csv(path / f"{ticker}.csv", index=False, encoding="utf-8-sig")


def test_generate_web_hot_pool_no_network_uses_cached_sources(tmp_path):
    """--no-network 时只使用本地缓存来源，并生成失败清单表头。"""
    cache_dir = tmp_path / "daily"
    cache_dir.mkdir()
    _write_daily_cache(cache_dir, "NBIS")
    stock_pool = tmp_path / "股票池.csv"
    pd.DataFrame({"代码": ["NBIS"], "名称": ["Nebius"], "是否ETF": ["否"]}).to_csv(stock_pool, index=False, encoding="utf-8-sig")
    output = tmp_path / "网上热度池.csv"
    report = tmp_path / "报告.md"
    failures = tmp_path / "失败.csv"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/生成网上热度池.py",
            "--no-network",
            "--limit",
            "500",
            "--cache-dir",
            str(cache_dir),
            "--stock-pool",
            str(stock_pool),
            "--output",
            str(output),
            "--report",
            str(report),
            "--failure-output",
            str(failures),
        ],
        cwd=项目根目录,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    pool = pd.read_csv(output, encoding="utf-8-sig")
    assert "代码" in pool.columns
    assert "是否阶段新高" in pool.columns
    assert "NBIS" in set(pool["代码"])
    assert "Yahoo" not in report.read_text(encoding="utf-8")
    failure_df = pd.read_csv(failures, encoding="utf-8-sig")
    assert list(failure_df.columns) == ["来源键", "来源网站", "来源分类", "失败原因", "更新时间"]
