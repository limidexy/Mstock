import pandas as pd

from src.scoring.main_wave_score import score_trend_structure

from scoring_helpers import make_feature_row


def test_trend_score_never_exceeds_25():
    """趋势结构分不超过25分。"""
    result = score_trend_structure(pd.Series(make_feature_row()))

    assert 0 <= result.score <= 25
    assert "均线多头排列" in result.reasons
