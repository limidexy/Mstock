import pandas as pd
import pytest

from src.scoring.scoring_pipeline import score_feature_dataframe, score_feature_row
from src.scoring.similarity_score import get_grade

from scoring_helpers import make_feature_dataframe, make_feature_row


def test_grade_rules_are_correct():
    """等级规则正确。"""
    assert get_grade(85) == ("A+", "核心主升浪候选")
    assert get_grade(75) == ("A", "强趋势候选")
    assert get_grade(65) == ("B", "观察候选")
    assert get_grade(50) == ("C", "形态不完整")
    assert get_grade(49.99) == ("D", "不符合风格")


def test_score_row_has_explanation_and_score_range():
    """单行评分包含解释，综合评分在0到100。"""
    result = score_feature_row(pd.Series(make_feature_row()))

    assert 0 <= result["综合评分"] <= 100
    assert result["主升浪形态分"] <= 10
    assert result["入选理由"]
    assert result["风险标签"]
    assert result["评分解释"]


def test_score_dataframe_does_not_mutate_input_and_sorts_descending():
    """评分 DataFrame 不修改输入，并按综合评分降序。"""
    df = make_feature_dataframe()
    original = df.copy(deep=True)

    scored = score_feature_dataframe(df)

    pd.testing.assert_frame_equal(df, original)
    assert scored["综合评分"].is_monotonic_decreasing


def test_missing_required_columns_raise_chinese_error():
    """缺失必要字段时抛出中文错误。"""
    with pytest.raises(ValueError, match="缺少必要字段"):
        score_feature_dataframe(pd.DataFrame({"代码": ["AAPL"]}))


def test_risk_penalty_lowers_total_score_and_strong_beats_weak():
    """风险扣分会降低综合评分，强趋势样本高于弱势样本。"""
    strong = score_feature_row(pd.Series(make_feature_row()))
    risky = score_feature_row(pd.Series(make_feature_row(risky=True)))
    weak = score_feature_row(pd.Series(make_feature_row(strong=False)))

    assert risky["风险扣分"] > strong["风险扣分"]
    assert risky["综合评分"] < strong["综合评分"]
    assert strong["综合评分"] > weak["综合评分"]
