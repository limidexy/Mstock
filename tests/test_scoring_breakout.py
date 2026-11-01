import pandas as pd

from src.scoring.main_wave_score import score_breakout_strength

from scoring_helpers import make_feature_row


def test_breakout_score_never_exceeds_25():
    """突破强度分不超过25分。"""
    result = score_breakout_strength(pd.Series(make_feature_row()))

    assert 0 <= result.score <= 25
    assert "突破20日新高" in result.reasons
