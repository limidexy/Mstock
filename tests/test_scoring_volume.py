import pandas as pd

from src.scoring.main_wave_score import score_volume_strength

from scoring_helpers import make_feature_row


def test_volume_score_never_exceeds_15():
    """量能强度分不超过15分。"""
    result = score_volume_strength(pd.Series(make_feature_row()))

    assert 0 <= result.score <= 15
    assert result.reasons
