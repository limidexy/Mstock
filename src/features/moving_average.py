"""均线特征计算。

所有滚动计算只使用当前行及其之前的数据，严格避免未来函数。
"""

from __future__ import annotations

import pandas as pd


默认均线周期 = (5, 10, 20, 30, 50, 60, 120, 250)
站上均线周期 = (5, 10, 20, 30, 50, 60)
默认涨幅周期 = (3, 5, 10, 20, 60)


def 准备日线数据(df: pd.DataFrame) -> pd.DataFrame:
    """复制并按日期升序整理日线数据。"""
    required_columns = ["日期", "收盘价"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"均线特征计算失败：缺少字段：{missing_columns}")

    output = df.copy()
    output["日期"] = pd.to_datetime(output["日期"])
    output["收盘价"] = pd.to_numeric(output["收盘价"], errors="coerce")
    output = output.sort_values("日期").reset_index(drop=True)
    if output["收盘价"].isna().any():
        raise ValueError("均线特征计算失败：收盘价存在缺失或无法转换的值。")
    output["日期"] = output["日期"].dt.strftime("%Y-%m-%d")
    return output


def 添加均线特征(df: pd.DataFrame, windows: tuple[int, ...] = 默认均线周期) -> pd.DataFrame:
    """添加均线、乖离和均线结构特征。"""
    output = 准备日线数据(df)
    output["当日涨幅"] = output["收盘价"].pct_change()
    for period in 默认涨幅周期:
        output[f"{period}日涨幅"] = output["收盘价"] / output["收盘价"].shift(period) - 1

    for window in windows:
        ma_column = f"MA{window}"
        output[ma_column] = output["收盘价"].rolling(window=window, min_periods=window).mean()
        output[f"MA{window}乖离"] = output["收盘价"] / output[ma_column] - 1
        output[f"MA{window}斜率"] = output[ma_column] / output[ma_column].shift(1) - 1

    for window in 站上均线周期:
        output[f"是否站上MA{window}"] = (output["收盘价"] > output[f"MA{window}"]).map({True: "是", False: "否"})

    output["是否均线多头排列"] = (
        (output["MA5"] > output["MA10"])
        & (output["MA10"] > output["MA20"])
        & (output["MA20"] > output["MA50"])
    ).map({True: "是", False: "否"})
    output["是否短期均线向上发散"] = (
        (output["MA5斜率"] > 0)
        & (output["MA10斜率"] > 0)
        & (output["MA5乖离"] > output["MA10乖离"])
    ).map({True: "是", False: "否"})
    output["是否主升浪加速"] = (
        (output["是否均线多头排列"] == "是")
        & (output["是否短期均线向上发散"] == "是")
        & (output["20日涨幅"] > 0)
        & (output["60日涨幅"] > 0)
    ).map({True: "是", False: "否"})

    return output
