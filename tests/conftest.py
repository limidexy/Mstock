"""为原有文件型集成测试提供隔离样本，不依赖或改写真实行情。"""

from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest


项目根目录 = Path(__file__).resolve().parents[1]
隔离模块 = {
    "test_candidate_output", "test_chart_generation", "test_review_output",
    "test_feature_sample_output", "test_feature_value_sanity",
    "test_scoring_sample_output", "test_generate_candidates_script",
    "test_generate_html_report_script", "test_generate_web_hot_pool",
    "test_expand_real_data_validation", "test_html_report", "test_universe_selection",
}


@pytest.fixture(scope="session")
def isolated_project(tmp_path_factory):
    """构造可离线运行脚本的临时项目与明确标记的模拟数据。"""
    from scripts.生成技术特征样例 import 计算单票特征
    from src.features.required_columns import get_required_feature_columns
    from src.reports.csv_report import 保存候选票_csv, 生成候选票
    from src.scoring.scoring_pipeline import score_feature_dataframe

    root = tmp_path_factory.mktemp("迁移隔离项目")
    for directory in ("src", "scripts", "config"):
        shutil.copytree(项目根目录 / directory, root / directory,
                        ignore=shutil.ignore_patterns("__pycache__"))
    for directory in ("raw", "processed", "cache/daily", "review", "output"):
        (root / "data" / directory).mkdir(parents=True, exist_ok=True)

    tickers = ["AA"] + [f"TEST{i:03d}" for i in range(1, 20)] + ["QQQ", "SPY"]
    dates = pd.bdate_range("2025-01-01", periods=300).strftime("%Y-%m-%d")
    daily_frames = {}
    for index, ticker in enumerate(tickers):
        growth = 0.0003 if ticker == "SPY" else 0.0005 if ticker == "QQQ" else 0.002 + index * 0.00002
        closes = 50 * (1 + growth) ** np.arange(300)
        volumes = np.full(300, 1_000_000)
        volumes[-1] = 3_000_000
        daily = pd.DataFrame({
            "日期": dates, "代码": ticker, "开盘价": closes * 0.999,
            "最高价": closes * 1.0001, "最低价": closes * 0.998,
            "收盘价": closes, "复权收盘价": closes, "成交量": volumes,
            "数据来源": "模拟测试样本", "更新时间": "2026-01-01 00:00:00",
        })
        daily.to_csv(root / "data/cache/daily" / f"{ticker}.csv", index=False, encoding="utf-8-sig")
        daily_frames[ticker] = daily

    metadata = [{"代码": ticker, "名称": f"模拟测试公司{ticker}", "市场": "NASDAQ",
                 "是否ETF": "是" if ticker in {"QQQ", "SPY"} else "否",
                 "是否测试证券": "否"} for ticker in tickers]
    # 分层抽样测试需要不同字母开头的股票池，但不需要为它们生成行情。
    metadata.extend({"代码": f"{letter}{i:03d}", "名称": "模拟测试普通股", "市场": "NYSE",
                     "是否ETF": "否", "是否测试证券": "否"}
                    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for i in range(20))
    pool = root / "data/processed/美股股票池.csv"
    pd.DataFrame(metadata).drop_duplicates("代码").to_csv(pool, index=False, encoding="utf-8-sig")
    samples = [计算单票特征(daily_frames[ticker], daily_frames["QQQ"], daily_frames["SPY"])
               .tail(1)[get_required_feature_columns()] for ticker in tickers[:-2]]
    features = pd.concat(samples, ignore_index=True)
    features.to_csv(root / "data/output/技术特征样例.csv", index=False, encoding="utf-8-sig")
    score_feature_dataframe(features).to_csv(root / "data/output/评分样例.csv", index=False, encoding="utf-8-sig")
    candidates = 生成候选票(root / "data/cache/daily", pool, top=20)
    保存候选票_csv(candidates.candidates, root / "data/output/今日候选票.csv")
    return root


@pytest.fixture(autouse=True)
def isolate_file_based_tests(request, monkeypatch):
    """仅重定向既有文件型测试的路径，不替换待测业务函数。"""
    module = request.module
    if module.__name__.split(".")[-1] not in 隔离模块:
        return
    root = request.getfixturevalue("isolated_project")
    monkeypatch.setattr(module, "项目根目录", root)
    if hasattr(module, "样例路径"):
        monkeypatch.setattr(module, "样例路径", root / "data/output/技术特征样例.csv")
    if module.__name__.endswith("test_expand_real_data_validation"):
        from scripts import 扩大真实数据验证 as validation
        for name, value in vars(validation).copy().items():
            if isinstance(value, Path) and value.is_relative_to(项目根目录):
                monkeypatch.setattr(validation, name, root / value.relative_to(项目根目录))
