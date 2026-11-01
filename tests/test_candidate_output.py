from pathlib import Path

import pandas as pd

from src.features.required_columns import 基准代码
from src.reports.csv_report import (
    候选票核心字段,
    从评分样例生成候选,
    保存候选票_csv,
    保存失败清单,
    失败清单字段,
    生成候选票,
    过滤候选,
)


项目根目录 = Path(__file__).resolve().parents[1]


def test_candidate_generation_contains_required_chinese_fields_and_excludes_benchmark():
    """候选票包含核心中文字段，并默认排除 QQQ、SPY。"""
    result = 生成候选票(
        cache_dir=项目根目录 / "data" / "cache" / "daily",
        stock_pool_path=项目根目录 / "data" / "processed" / "美股股票池.csv",
        top=20,
    )

    missing = [field for field in 候选票核心字段 if field not in result.candidates.columns]
    assert not missing, f"候选票缺少字段：{missing}"
    assert not set(result.candidates["代码"]).intersection(set(基准代码))
    assert len(result.candidates) <= 20
    assert result.candidates["综合评分"].between(0, 100).all()
    assert result.candidates["综合评分"].is_monotonic_decreasing
    assert result.candidates["排名"].tolist() == list(range(1, len(result.candidates) + 1))
    assert result.candidates["风险标签"].astype(str).str.strip().ne("").all()
    assert result.candidates["入选理由"].astype(str).str.strip().ne("").all()
    assert result.candidates["评分解释"].astype(str).str.strip().ne("").all()


def test_candidate_filters_do_not_mutate_input():
    """候选过滤不原地修改输入 DataFrame。"""
    result = 生成候选票(
        cache_dir=项目根目录 / "data" / "cache" / "daily",
        stock_pool_path=项目根目录 / "data" / "processed" / "美股股票池.csv",
        top=20,
    )
    source = result.candidates.copy(deep=True)
    original = source.copy(deep=True)

    filtered = 过滤候选(source, top=5, min_score=0, min_grade="D")

    pd.testing.assert_frame_equal(source, original)
    assert len(filtered) <= 5


def test_candidate_csv_and_failure_csv_use_chinese_headers_and_bom(tmp_path):
    """候选票和失败清单保存为 utf-8-sig，失败清单为空也有表头。"""
    result = 生成候选票(
        cache_dir=项目根目录 / "data" / "cache" / "daily",
        stock_pool_path=项目根目录 / "data" / "processed" / "美股股票池.csv",
        top=5,
    )
    candidate_path = tmp_path / "今日候选票.csv"
    failure_path = tmp_path / "候选票失败清单.csv"

    保存候选票_csv(result.candidates, candidate_path)
    保存失败清单(pd.DataFrame(columns=失败清单字段), failure_path)

    assert candidate_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert failure_path.read_bytes().startswith(b"\xef\xbb\xbf")
    failure = pd.read_csv(failure_path, encoding="utf-8-sig")
    assert failure.columns.tolist() == 失败清单字段


def test_candidate_generation_from_score_sample_is_supported():
    """调试模式可以从评分样例生成候选票。"""
    result = 从评分样例生成候选(
        score_sample_path=项目根目录 / "data" / "output" / "评分样例.csv",
        stock_pool_path=项目根目录 / "data" / "processed" / "美股股票池.csv",
        top=10,
        min_score=0,
        min_grade="D",
        include_benchmark=False,
    )

    assert result.used_score_sample is True
    assert len(result.candidates) <= 10
    assert [field for field in 候选票核心字段 if field not in result.candidates.columns] == []


def test_missing_stock_pool_metadata_does_not_fail(tmp_path):
    """股票池元数据缺失时不导致候选票生成失败。"""
    result = 生成候选票(
        cache_dir=项目根目录 / "data" / "cache" / "daily",
        stock_pool_path=tmp_path / "不存在的股票池.csv",
        top=5,
    )

    assert result.metadata_warning
    assert len(result.candidates) <= 5
    if not result.candidates.empty:
        assert result.candidates["名称"].eq("不足数据").all()
