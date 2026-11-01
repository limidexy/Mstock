from pathlib import Path

import pandas as pd

from src.data.universe_selection import (
    下载候选池字段,
    分层抽样补足,
    构建下载候选池,
    清洗股票池,
)
from src.scoring.scoring_pipeline import 必要评分输入字段


项目根目录 = Path(__file__).resolve().parents[1]


def test_download_candidate_pool_contains_benchmark_and_unique(tmp_path):
    """下载候选池包含 QQQ、SPY，并且代码去重。"""
    output_path = tmp_path / "下载候选池.csv"
    result = 构建下载候选池(
        stock_pool_path=项目根目录 / "data" / "processed" / "美股股票池.csv",
        target_size=80,
        output_path=output_path,
    )

    codes = result.数据["代码"].tolist()
    assert {"QQQ", "SPY"}.issubset(set(codes))
    assert len(codes) == len(set(codes))
    assert result.数据.columns.tolist() == 下载候选池字段


def test_download_candidate_pool_is_not_alphabet_front_only(tmp_path):
    """候选池不是简单取字母表前排。"""
    result = 构建下载候选池(
        stock_pool_path=项目根目录 / "data" / "processed" / "美股股票池.csv",
        target_size=200,
        output_path=tmp_path / "下载候选池_200.csv",
    )

    first_letters = set(result.数据["代码"].str[0])
    assert len(first_letters) >= 10
    assert not result.数据["代码"].tolist() == sorted(result.数据["代码"].tolist())[: len(result.数据)]


def test_seed_list_is_not_used_for_score_bonus(tmp_path):
    """验证种子只用于下载覆盖，不进入评分加分字段。"""
    result = 构建下载候选池(
        stock_pool_path=项目根目录 / "data" / "processed" / "美股股票池.csv",
        target_size=40,
        output_path=tmp_path / "下载候选池.csv",
    )

    assert "综合评分" not in result.数据.columns
    assert "候选池来源" not in 必要评分输入字段
    assert "入选原因" not in 必要评分输入字段


def test_stratified_sampling_can_fill_target_size():
    """股票池足够时，分层抽样可以补足目标数量。"""
    rows = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for index in range(4):
            rows.append(
                {
                    "代码": f"{letter}{index:03d}",
                    "名称": f"{letter} 示例公司 {index}",
                    "市场": "NASDAQ",
                    "是否ETF": "是" if index == 0 else "否",
                    "是否测试证券": "否",
                }
            )
    pool = 清洗股票池(pd.DataFrame(rows))
    sampled = 分层抽样补足(pool, 已选代码=set(), 需要数量=60)

    assert len(sampled) == 60
    assert len({row["代码"][0] for row in sampled}) >= 20


def test_clean_stock_pool_filters_test_and_non_target_symbols():
    """清洗股票池会过滤测试证券和明显非普通标的。"""
    df = pd.DataFrame(
        [
            {"代码": "GOOD", "名称": "Good Company Common Stock", "市场": "NASDAQ", "是否ETF": "否", "是否测试证券": "否"},
            {"代码": "TEST", "名称": "Test Company Common Stock", "市场": "NASDAQ", "是否ETF": "否", "是否测试证券": "是"},
            {"代码": "WRT", "名称": "Example Warrants", "市场": "NASDAQ", "是否ETF": "否", "是否测试证券": "否"},
            {"代码": "UNT", "名称": "Example Units", "市场": "NASDAQ", "是否ETF": "否", "是否测试证券": "否"},
            {"代码": "PFD$A", "名称": "Example Preferred Shares", "市场": "NYSE", "是否ETF": "否", "是否测试证券": "否"},
            {"代码": "ETF1", "名称": "Example ETF", "市场": "NYSE Arca", "是否ETF": "是", "是否测试证券": "否"},
        ]
    )

    cleaned = 清洗股票池(df)

    assert set(cleaned["代码"]) == {"GOOD", "ETF1"}
