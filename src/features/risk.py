"""风险特征计算。

风险标签只用于人工复核，不构成买卖建议。
"""

from __future__ import annotations

import pandas as pd

from src.features.moving_average import 添加均线特征, 准备日线数据


def 添加风险特征(df: pd.DataFrame) -> pd.DataFrame:
    """添加波动、回撤、上影线和中文风险标签。"""
    required_columns = ["最高价", "最低价", "开盘价", "成交量"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"风险特征计算失败：缺少字段：{missing_columns}")

    output = df.copy()
    if "MA5" not in output.columns or "MA10" not in output.columns:
        output = 添加均线特征(output)
    else:
        output = 准备日线数据(output)

    for column in ["最高价", "最低价", "开盘价", "成交量"]:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    if output[["最高价", "最低价", "开盘价", "成交量"]].isna().any().any():
        raise ValueError("风险特征计算失败：价格或成交量存在缺失。")

    output["日收益率"] = output["收盘价"].pct_change()
    output["20日波动率"] = output["日收益率"].rolling(window=20, min_periods=20).std()
    rolling_high = output["收盘价"].rolling(window=60, min_periods=20).max()
    output["60日回撤"] = output["收盘价"] / rolling_high - 1
    candle_range = (output["最高价"] - output["最低价"]).replace(0, pd.NA)
    output["上影线比例"] = (output["最高价"] - output[["开盘价", "收盘价"]].max(axis=1)) / candle_range
    output["是否距离MA5过远"] = (output["MA5乖离"] > 0.10).map({True: "是", False: "否"})
    output["是否距离MA10过远"] = (output["MA10乖离"] > 0.15).map({True: "是", False: "否"})
    output["是否距离MA20过远"] = (output["MA20乖离"] > 0.20).map({True: "是", False: "否"})
    output["是否连续加速过热"] = ((output["3日涨幅"] > 0.12) & (output["MA5乖离"] > 0.08)).map({True: "是", False: "否"})
    output["是否长上影线"] = (output["上影线比例"] > 0.45).map({True: "是", False: "否"})
    output["是否缩量冲高"] = (
        (output.get("当日涨幅", pd.Series(index=output.index, dtype=float)) > 0)
        & (output.get("是否缩量", pd.Series("否", index=output.index)) == "是")
    ).map({True: "是", False: "否"})
    if "成交额" not in output.columns:
        output["成交额"] = output["收盘价"] * output["成交量"]
    output["是否流动性不足"] = ((output["成交额"] < 1_000_000) | (output["成交量"] < 100_000)).map({True: "是", False: "否"})
    output["是否高波动"] = (output["20日波动率"] > 0.04).map({True: "是", False: "否"})
    output["是否高波动风险"] = (output["20日波动率"] > 0.04).map({True: "是", False: "否"})
    output["是否回撤偏大"] = (output["60日回撤"] < -0.15).map({True: "是", False: "否"})
    output["风险标签"] = output.apply(_生成风险标签, axis=1)
    return output


def _生成风险标签(row: pd.Series) -> str:
    """生成中文风险标签。"""
    tags: list[str] = []
    if row.get("是否距离MA5过远") == "是":
        tags.append("距离MA5过远")
    if row.get("是否距离MA10过远") == "是":
        tags.append("距离MA10过远")
    if row.get("是否距离MA20过远") == "是":
        tags.append("距离MA20过远")
    if row.get("是否连续加速过热") == "是":
        tags.append("连续加速过热")
    if row.get("是否高波动风险") == "是":
        tags.append("高波动风险")
    if row.get("是否长上影线") == "是":
        tags.append("长上影线")
    if row.get("是否缩量冲高") == "是":
        tags.append("缩量冲高")
    if row.get("是否流动性不足") == "是":
        tags.append("流动性不足")
    return "；".join(tags) if tags else "无明显风险"
