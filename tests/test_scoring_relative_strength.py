import pandas as pd

from src.scoring.main_wave_score import score_relative_strength

from scoring_helpers import make_feature_row


def test_relative_strength_score_never_exceeds_15():
    """相对强度分不超过15分。"""
    result = score_relative_strength(pd.Series(make_feature_row()))

    assert 0 <= result.score <= 15
    assert "20日强于QQQ" in result.reasons
