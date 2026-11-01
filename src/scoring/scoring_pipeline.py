"""主升浪相似度评分管道。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.scoring.main_wave_score import (
    score_breakout_strength,
    score_main_wave_shape,
    score_relative_strength,
    score_trend_structure,
    score_volume_strength,
)
from src.scoring.risk_penalty import score_risk_penalty
from src.scoring.similarity_score import clamp_total_score, get_grade, normalize_risk_tags, pick_stop_level, to_number


评分输出字段 = [
    "排名",
    "代码",
    "日期",
    "收盘价",
    "成交额",
    "当日涨幅",
    "5日涨幅",
    "10日涨幅",
    "20日涨幅",
    "60日涨幅",
    "趋势结构分",
    "突破强度分",
    "量能强度分",
    "相对强度分",
    "主升浪形态分",
    "风险扣分",
    "综合评分",
    "等级",
    "等级说明",
    "入选理由",
    "风险标签",
    "评分解释",
    "观察价",
    "失效位",
]

必要评分输入字段 = [
    "代码",
    "日期",
    "收盘价",
    "成交额",
    "当日涨幅",
    "5日涨幅",
    "10日涨幅",
    "20日涨幅",
    "60日涨幅",
    "是否站上MA5",
    "是否站上MA10",
    "是否站上MA20",
    "是否站上MA60",
    "是否均线多头排列",
    "是否短期均线向上发散",
    "是否突破20日新高",
    "是否突破60日新高",
    "是否突破120日新高",
    "距离20日新高",
    "距离60日新高",
    "是否收盘接近日高",
    "是否主升浪加速",
    "20日量比",
    "成交额放大倍数",
    "是否放量",
    "是否明显放量",
    "是否缩量",
    "是否5日强于QQQ",
    "是否10日强于QQQ",
    "是否20日强于QQQ",
    "是否60日强于QQQ",
    "是否5日强于SPY",
    "是否10日强于SPY",
    "是否20日强于SPY",
    "是否60日强于SPY",
    "突破状态",
    "风险标签",
    "是否距离MA5过远",
    "是否距离MA10过远",
    "是否距离MA20过远",
    "是否连续加速过热",
    "是否长上影线",
    "是否缩量冲高",
    "是否流动性不足",
    "是否高波动",
    "MA10",
    "MA20",
]


@dataclass(frozen=True)
class ScoringResult:
    """评分结果和失败清单。"""

    scored: pd.DataFrame
    failures: pd.DataFrame


def validate_scoring_input_columns(df: pd.DataFrame) -> None:
    """校验评分输入字段。"""
    missing = [column for column in 必要评分输入字段 if column not in df.columns]
    if missing:
        raise ValueError(f"评分失败：缺少必要字段：{missing}")


def score_feature_row(row: pd.Series) -> dict[str, Any]:
    """对单行技术特征计算主升浪相似度评分。"""
    trend = score_trend_structure(row)
    breakout = score_breakout_strength(row)
    volume = score_volume_strength(row)
    relative = score_relative_strength(row)
    shape = score_main_wave_shape(row)
    risk = score_risk_penalty(row)

    raw_score = trend.score + breakout.score + volume.score + relative.score + shape.score - risk.score
    total_score = round(clamp_total_score(raw_score), 2)
    grade, grade_description = get_grade(total_score)
    risk_tags = normalize_risk_tags(row.get("风险标签"))
    reasons = _merge_reasons([trend.reasons, breakout.reasons, volume.reasons, relative.reasons, shape.reasons])
    if not reasons:
        reasons = ["未触发明显主升浪特征"]

    explanation_parts = [
        trend.explanation("趋势结构分"),
        breakout.explanation("突破强度分"),
        volume.explanation("量能强度分"),
        relative.explanation("相对强度分"),
        shape.explanation("主升浪形态分"),
        risk.explanation("风险扣分"),
    ]

    result = {
        "代码": row.get("代码"),
        "日期": row.get("日期"),
        "收盘价": to_number(row.get("收盘价")),
        "成交额": to_number(row.get("成交额")),
        "当日涨幅": to_number(row.get("当日涨幅")),
        "5日涨幅": to_number(row.get("5日涨幅")),
        "10日涨幅": to_number(row.get("10日涨幅")),
        "20日涨幅": to_number(row.get("20日涨幅")),
        "60日涨幅": to_number(row.get("60日涨幅")),
        "趋势结构分": trend.score,
        "突破强度分": breakout.score,
        "量能强度分": volume.score,
        "相对强度分": relative.score,
        "主升浪形态分": shape.score,
        "风险扣分": risk.score,
        "综合评分": total_score,
        "等级": grade,
        "等级说明": grade_description,
        "入选理由": "；".join(reasons),
        "风险标签": risk_tags,
        "评分解释": "；".join(explanation_parts) + "。",
        "观察价": to_number(row.get("收盘价")),
        "失效位": pick_stop_level(row),
    }
    return result


def score_feature_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """对技术特征 DataFrame 评分，并按综合评分降序输出。"""
    validate_scoring_input_columns(df)
    result = score_feature_dataframe_with_failures(df)
    return result.scored


def score_feature_dataframe_with_failures(df: pd.DataFrame) -> ScoringResult:
    """对技术特征 DataFrame 评分，单行失败不会中断整体流程。"""
    validate_scoring_input_columns(df)
    source = df.copy(deep=True)
    scored_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, row in source.iterrows():
        try:
            scored_rows.append(score_feature_row(row))
        except Exception as exc:
            failures.append({"代码": row.get("代码", ""), "失败原因": f"评分失败：{exc}", "行号": index})

    scored = pd.DataFrame(scored_rows)
    if not scored.empty:
        scored = scored.sort_values(["综合评分", "代码"], ascending=[False, True]).reset_index(drop=True)
        scored.insert(0, "排名", range(1, len(scored) + 1))
        scored = scored[评分输出字段]
    else:
        scored = pd.DataFrame(columns=评分输出字段)
    failure_df = pd.DataFrame(failures, columns=["代码", "失败原因", "行号"])
    return ScoringResult(scored=scored, failures=failure_df)


def _merge_reasons(reason_groups: list[list[str]]) -> list[str]:
    """合并理由并保持顺序去重。"""
    seen = set()
    merged: list[str] = []
    for group in reason_groups:
        for reason in group:
            if reason and reason not in seen:
                seen.add(reason)
                merged.append(reason)
    return merged
