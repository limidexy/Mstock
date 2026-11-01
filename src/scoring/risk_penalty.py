"""风险扣分规则。"""

from __future__ import annotations

import pandas as pd

from src.scoring.similarity_score import ScoreResult, cap_score, is_yes, normalize_risk_tags


风险扣分上限 = 20


def score_risk_penalty(row: pd.Series) -> ScoreResult:
    """计算风险扣分，返回正数表示扣分。"""
    score = 0.0
    reasons: list[str] = []
    rules = [
        ("是否距离MA5过远", 4, "距离MA5过远"),
        ("是否距离MA10过远", 5, "距离MA10过远"),
        ("是否距离MA20过远", 6, "距离MA20过远"),
        ("是否连续加速过热", 5, "连续加速过热"),
        ("是否长上影线", 4, "长上影线"),
        ("是否缩量冲高", 5, "缩量冲高"),
        ("是否流动性不足", 6, "流动性不足"),
        ("是否高波动", 3, "高波动"),
    ]
    for field, points, reason in rules:
        if is_yes(row.get(field)):
            score += points
            reasons.append(reason)

    risk_tags = normalize_risk_tags(row.get("风险标签"))
    if risk_tags == "无明显风险" and not reasons:
        return ScoreResult(0.0, ["无明显风险"])
    return ScoreResult(cap_score(score, 风险扣分上限), reasons)
