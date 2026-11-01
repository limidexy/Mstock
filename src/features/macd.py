"""MACD 特征计算。

EMA 仅由当前及历史收盘价递推生成，不使用未来数据。
"""

from __future__ import annotations

import pandas as pd

from src.features.moving_average import 准备日线数据


def 添加MACD特征(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """添加 MACD DIF、DEA、柱体和中文状态。"""
    output = 准备日线数据(df)
    close = output["收盘价"]

    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    output["DIF"] = ema_fast - ema_slow
    output["DEA"] = output["DIF"].ewm(span=signal, adjust=False, min_periods=signal).mean()
    output["MACD柱"] = (output["DIF"] - output["DEA"]) * 2
    output["MACD柱变化"] = output["MACD柱"] - output["MACD柱"].shift(1)
    output["DIF前值"] = output["DIF"].shift(1)
    output["DEA前值"] = output["DEA"].shift(1)

    output["MACD状态"] = output.apply(_判断MACD状态, axis=1)
    output = output.drop(columns=["DIF前值", "DEA前值"])
    return output


def _判断MACD状态(row: pd.Series) -> str:
    """根据当前行判断 MACD 中文状态。"""
    if (
        pd.isna(row["DIF"])
        or pd.isna(row["DEA"])
        or pd.isna(row["MACD柱"])
        or pd.isna(row["MACD柱变化"])
        or pd.isna(row["DIF前值"])
        or pd.isna(row["DEA前值"])
    ):
        return "不足数据"
    if row["DIF"] > row["DEA"] and row["DIF前值"] <= row["DEA前值"]:
        return "金叉"
    if row["DIF"] < row["DEA"] and row["DIF前值"] >= row["DEA前值"]:
        return "死叉"
    if row["DIF"] > row["DEA"] and row["MACD柱变化"] >= 0:
        return "多头扩大"
    if row["DIF"] > row["DEA"] and row["MACD柱"] > 0:
        return "多头收缩"
    if row["DIF"] < row["DEA"] and row["MACD柱变化"] <= 0:
        return "空头扩大"
    if row["DIF"] < row["DEA"] and row["MACD柱"] < 0:
        return "空头收缩"
    return "不足数据"
