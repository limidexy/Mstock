"""量能特征计算。

成交量均值和量比均使用当前及历史数据。
"""

from __future__ import annotations

import pandas as pd

from src.features.moving_average import 准备日线数据


def 添加量能特征(df: pd.DataFrame) -> pd.DataFrame:
    """添加成交额、MAVOL、量比和量能状态。"""
    required_columns = ["成交量"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"量能特征计算失败：缺少字段：{missing_columns}")

    output = 准备日线数据(df)
    output["成交量"] = pd.to_numeric(output["成交量"], errors="coerce")
    if output["成交量"].isna().any():
        raise ValueError("量能特征计算失败：成交量存在缺失或无法转换的值。")

    output["成交额"] = output["收盘价"] * output["成交量"]
    for window in (5, 10, 20):
        output[f"MAVOL{window}"] = output["成交量"].rolling(window=window, min_periods=window).mean()
    output["成交额MA20"] = output["成交额"].rolling(window=20, min_periods=20).mean()
    output["20日量比"] = output["成交量"] / output["MAVOL20"]
    output["成交额放大倍数"] = output["成交额"] / output["成交额MA20"]
    output["是否放量"] = (output["20日量比"] >= 1.2).map({True: "是", False: "否"})
    output["是否明显放量"] = ((output["20日量比"] >= 1.8) & (output["成交额放大倍数"] >= 1.5)).map({True: "是", False: "否"})
    output["是否缩量"] = (output["20日量比"] <= 0.7).map({True: "是", False: "否"})
    output["量能状态"] = output.apply(_判断量能状态, axis=1)
    return output


def _判断量能状态(row: pd.Series) -> str:
    """判断中文量能状态。"""
    if pd.isna(row["20日量比"]):
        return "不足数据"
    if row["20日量比"] >= 1.8 and row["成交额放大倍数"] >= 1.5:
        return "明显放量"
    if row["20日量比"] >= 1.2:
        return "放量"
    if row["20日量比"] <= 0.7:
        return "缩量"
    return "正常"
