import pandas as pd

from src.scoring.risk_penalty import score_risk_penalty

from scoring_helpers import make_feature_row


def test_risk_penalty_never_exceeds_20_and_reacts_to_liquidity():
    """风险扣分不超过20分，流动性不足会扣分。"""
    normal = score_risk_penalty(pd.Series(make_feature_row()))
    risky = score_risk_penalty(pd.Series(make_feature_row(risky=True)))

    assert 0 <= normal.score <= 20
    assert 0 <= risky.score <= 20
    assert risky.score > normal.score
    assert "流动性不足" in risky.reasons
