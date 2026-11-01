"""相对强度特征计算。

相对强度使用历史区间收益差，不使用未来数据。
"""

from __future__ import annotations

import pandas as pd

from src.features.moving_average import 准备日线数据


默认相对强度周期 = (5, 10, 20, 60)


def 添加相对强度特征(
    df: pd.DataFrame,
    qqq_df: pd.DataFrame,
    spy_df: pd.DataFrame,
    periods: tuple[int, ...] = 默认相对强度周期,
) -> pd.DataFrame:
    """添加相对 QQQ / SPY 的区间强度特征。"""
    target = 准备日线数据(df)
    qqq = _准备基准数据(qqq_df, "QQQ")
    spy = _准备基准数据(spy_df, "SPY")

    output = target.merge(qqq, on="日期", how="left").merge(spy, on="日期", how="left")
    for period in periods:
        output[f"{period}日涨幅"] = output["收盘价"] / output["收盘价"].shift(period) - 1
        output[f"QQQ{period}日涨幅"] = output["QQQ收盘价"] / output["QQQ收盘价"].shift(period) - 1
        output[f"SPY{period}日涨幅"] = output["SPY收盘价"] / output["SPY收盘价"].shift(period) - 1
        output[f"相对QQQ{period}日强度"] = output[f"{period}日涨幅"] - output[f"QQQ{period}日涨幅"]
        output[f"相对SPY{period}日强度"] = output[f"{period}日涨幅"] - output[f"SPY{period}日涨幅"]
        output[f"是否{period}日强于QQQ"] = (output[f"相对QQQ{period}日强度"] > 0).map({True: "是", False: "否"})
        output[f"是否{period}日强于SPY"] = (output[f"相对SPY{period}日强度"] > 0).map({True: "是", False: "否"})

    output["相对QQQ强度"] = output["相对QQQ20日强度"]
    output["相对SPY强度"] = output["相对SPY20日强度"]
    output["相对强度状态"] = output.apply(_判断相对强度状态, axis=1)
    return output


def _准备基准数据(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """准备基准收盘价数据。"""
    output = 准备日线数据(df)
    return output[["日期", "收盘价"]].rename(columns={"收盘价": f"{prefix}收盘价"})


def _判断相对强度状态(row: pd.Series) -> str:
    """判断相对强度中文状态。"""
    if pd.isna(row["相对QQQ强度"]) or pd.isna(row["相对SPY强度"]):
        return "不足数据"
    if row["相对QQQ强度"] > 0 and row["相对SPY强度"] > 0:
        return "强于QQQ和SPY"
    if row["相对QQQ强度"] > 0:
        return "强于QQQ"
    if row["相对SPY强度"] > 0:
        return "强于SPY"
    return "弱于QQQ和SPY"
