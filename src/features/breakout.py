"""突破特征计算。

阶段新高使用前一日之前的滚动高点作为比较基准，避免当天最高价参与当天突破判断。
"""

from __future__ import annotations

import pandas as pd

from src.features.moving_average import 准备日线数据


默认突破周期 = (20, 60, 120)


def 添加突破特征(df: pd.DataFrame, windows: tuple[int, ...] = 默认突破周期) -> pd.DataFrame:
    """添加阶段新高、距离新高和突破状态特征。"""
    required_columns = ["最高价", "最低价"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"突破特征计算失败：缺少字段：{missing_columns}")

    output = 准备日线数据(df)
    output["最高价"] = pd.to_numeric(output["最高价"], errors="coerce")
    output["最低价"] = pd.to_numeric(output["最低价"], errors="coerce")
    if output[["最高价", "最低价"]].isna().any().any():
        raise ValueError("突破特征计算失败：最高价或最低价存在缺失。")

    for window in windows:
        high_column = f"前{window}日高点"
        output[high_column] = output["最高价"].rolling(window=window, min_periods=window).max().shift(1)
        output[f"距离{window}日新高"] = output["收盘价"] / output[high_column] - 1
        output[f"是否突破{window}日新高"] = (output["收盘价"] >= output[high_column]).map({True: "是", False: "否"})

    day_range = (output["最高价"] - output["最低价"]).replace(0, pd.NA)
    output["当日收盘位置"] = ((output["收盘价"] - output["最低价"]) / day_range).astype("Float64")
    output.loc[(output["最高价"] == output["最低价"]), "当日收盘位置"] = 0.5
    near_high = ((output["最高价"] - output["收盘价"]) / day_range <= 0.25).fillna(False)
    output["是否收盘接近日高"] = near_high.map({True: "是", False: "否"})
    output["突破状态"] = output.apply(_判断突破状态, axis=1)
    return output


def _判断突破状态(row: pd.Series) -> str:
    """判断中文突破状态。"""
    if pd.isna(row.get("前20日高点")):
        return "不足数据"
    if row.get("是否突破120日新高") == "是":
        return "突破120日新高"
    if row.get("是否突破60日新高") == "是":
        return "突破60日新高"
    if row.get("是否突破20日新高") == "是":
        return "突破20日新高"
    distance = row.get("距离20日新高")
    if pd.notna(distance) and distance >= -0.03:
        return "接近20日新高"
    return "未突破"
