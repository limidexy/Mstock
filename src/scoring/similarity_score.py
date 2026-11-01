"""主升浪相似度评分通用工具。"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ScoreResult:
    """单个评分分项结果。"""

    score: float
    reasons: list[str]

    def explanation(self, label: str) -> str:
        """生成中文解释片段。"""
        reason_text = "、".join(self.reasons) if self.reasons else "未触发明显加分项"
        return f"{label}{self.score:g}：{reason_text}"


def to_number(value: Any, default: float = 0.0) -> float:
    """安全转换为数字。"""
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def is_yes(value: Any) -> bool:
    """判断中文布尔字段是否为是。"""
    return str(value).strip() == "是"


def cap_score(score: float, maximum: float) -> float:
    """限制分项分数不超过上限。"""
    return min(max(float(score), 0.0), float(maximum))


def clamp_total_score(score: float) -> float:
    """限制综合评分在 0 到 100。"""
    return min(max(float(score), 0.0), 100.0)


def get_grade(score: float) -> tuple[str, str]:
    """根据综合评分返回等级和等级说明。"""
    score = float(score)
    if score >= 85:
        return "A+", "核心主升浪候选"
    if score >= 75:
        return "A", "强趋势候选"
    if score >= 65:
        return "B", "观察候选"
    if score >= 50:
        return "C", "形态不完整"
    return "D", "不符合风格"


def normalize_risk_tags(value: Any) -> str:
    """规范风险标签，空值统一为无明显风险。"""
    text = str(value).strip()
    if text in {"", "无", "None", "nan", "NaN"}:
        return "无明显风险"
    return text.replace(";", "；")


def pick_stop_level(row: pd.Series) -> float | None:
    """选择初版失效位，优先 MA10，其次 MA20。"""
    ma10 = to_number(row.get("MA10"), default=float("nan"))
    if not math.isnan(ma10):
        return ma10
    ma20 = to_number(row.get("MA20"), default=float("nan"))
    if not math.isnan(ma20):
        return ma20
    return None
