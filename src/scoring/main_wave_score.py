"""主升浪风格各分项评分。"""

from __future__ import annotations

import pandas as pd

from src.scoring.similarity_score import ScoreResult, cap_score, is_yes, to_number


趋势结构最高分 = 25
突破强度最高分 = 25
量能强度最高分 = 15
相对强度最高分 = 15
主升浪形态最高分 = 10


def score_trend_structure(row: pd.Series) -> ScoreResult:
    """计算趋势结构分，最高 25 分。"""
    score = 0.0
    reasons: list[str] = []
    rules = [
        ("是否站上MA5", 3, "站上MA5"),
        ("是否站上MA10", 3, "站上MA10"),
        ("是否站上MA20", 3, "站上MA20"),
        ("是否站上MA60", 3, "站上MA60"),
        ("是否均线多头排列", 6, "均线多头排列"),
        ("是否短期均线向上发散", 4, "短期均线向上发散"),
    ]
    for field, points, reason in rules:
        if is_yes(row.get(field)):
            score += points
            reasons.append(reason)
    if to_number(row.get("20日涨幅")) > 0:
        score += 2
        reasons.append("20日趋势向上")
    if to_number(row.get("5日涨幅")) > 0 and to_number(row.get("10日涨幅")) > 0:
        score += 1
        reasons.append("短线趋势向上")
    return ScoreResult(cap_score(score, 趋势结构最高分), reasons)


def score_breakout_strength(row: pd.Series) -> ScoreResult:
    """计算突破强度分，最高 25 分。"""
    score = 0.0
    reasons: list[str] = []
    rules = [
        ("是否突破20日新高", 6, "突破20日新高"),
        ("是否突破60日新高", 7, "突破60日新高"),
        ("是否突破120日新高", 8, "突破120日新高"),
        ("是否收盘接近日高", 3, "收盘接近日高"),
        ("是否主升浪加速", 4, "主升浪加速"),
    ]
    for field, points, reason in rules:
        if is_yes(row.get(field)):
            score += points
            reasons.append(reason)
    if to_number(row.get("距离20日新高"), default=-999) >= -0.03:
        score += 3
        reasons.append("接近20日新高")
    if to_number(row.get("距离60日新高"), default=-999) >= -0.05:
        score += 2
        reasons.append("接近60日新高")
    if to_number(row.get("当日涨幅")) > 0:
        score += 1
        reasons.append("当日上涨")
    return ScoreResult(cap_score(score, 突破强度最高分), reasons)


def score_volume_strength(row: pd.Series) -> ScoreResult:
    """计算量能强度分，最高 15 分。"""
    score = 0.0
    reasons: list[str] = []
    if is_yes(row.get("是否明显放量")):
        score += 6
        reasons.append("明显放量")
    elif is_yes(row.get("是否放量")):
        score += 4
        reasons.append("放量")
    if to_number(row.get("20日量比")) >= 2:
        score += 3
        reasons.append("量比超过2")
    amount = to_number(row.get("成交额"))
    if amount >= 10_000_000:
        score += 3
        reasons.append("成交额充足")
    if amount >= 50_000_000:
        score += 2
        reasons.append("成交额较大")
    if to_number(row.get("成交额放大倍数")) >= 1.2:
        score += 2
        reasons.append("成交额明显放大")
    return ScoreResult(cap_score(score, 量能强度最高分), reasons)


def score_relative_strength(row: pd.Series) -> ScoreResult:
    """计算相对强度分，最高 15 分。"""
    score = 0.0
    reasons: list[str] = []
    rules = [
        ("是否5日强于QQQ", 2, "5日强于QQQ"),
        ("是否10日强于QQQ", 2, "10日强于QQQ"),
        ("是否20日强于QQQ", 3, "20日强于QQQ"),
        ("是否60日强于QQQ", 2, "60日强于QQQ"),
        ("是否5日强于SPY", 1, "5日强于SPY"),
        ("是否10日强于SPY", 1, "10日强于SPY"),
        ("是否20日强于SPY", 2, "20日强于SPY"),
        ("是否60日强于SPY", 2, "60日强于SPY"),
    ]
    for field, points, reason in rules:
        if is_yes(row.get(field)):
            score += points
            reasons.append(reason)
    if score >= 8:
        reasons.append("相对强度占优")
    return ScoreResult(cap_score(score, 相对强度最高分), reasons)


def score_main_wave_shape(row: pd.Series) -> ScoreResult:
    """计算主升浪形态分，最高 10 分。"""
    score = 0.0
    reasons: list[str] = []
    if is_yes(row.get("是否均线多头排列")) and is_yes(row.get("是否短期均线向上发散")):
        score += 3
        reasons.append("主升浪结构清晰")
    if is_yes(row.get("是否主升浪加速")):
        score += 2
        reasons.append("主升浪加速")
    if str(row.get("突破状态", "")).strip() not in {"", "未突破", "不足数据"}:
        score += 2
        reasons.append("突破结构有效")
    if to_number(row.get("20日涨幅")) > 0 and to_number(row.get("60日涨幅")) > 0:
        score += 1
        reasons.append("趋势延续")
    if is_yes(row.get("是否收盘接近日高")):
        score += 1
        reasons.append("收盘强势")
    if str(row.get("风险标签", "")).strip() == "无明显风险":
        score += 1
        reasons.append("风险较少")
    return ScoreResult(cap_score(score, 主升浪形态最高分), reasons)
