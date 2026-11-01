"""待校对 CSV 输出。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


人工校对字段 = [
    "我的校对",
    "我的备注",
    "是否加入观察池",
    "是否实际交易",
    "交易结果",
    "复盘日期",
]

校对选项提示 = ["像", "不像", "太高", "太弱", "可观察", "准备交易", "等回踩", "不符合风格"]


def 默认待校对路径(review_dir: Path | str = Path("data/review")) -> Path:
    """返回当天待校对 CSV 默认路径。"""
    today = datetime.now().strftime("%Y%m%d")
    return Path(review_dir) / f"待校对_{today}.csv"


def 生成待校对表(candidates: pd.DataFrame, review_date: str | None = None) -> pd.DataFrame:
    """在候选票基础上增加人工校对字段。"""
    output = candidates.copy()
    review_date = review_date or datetime.now().strftime("%Y-%m-%d")
    for column in 人工校对字段:
        output[column] = ""
    output["复盘日期"] = review_date
    return output


def 保存待校对_csv(candidates: pd.DataFrame, path: Path | str) -> Path:
    """保存待校对 CSV。"""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    review_df = 生成待校对表(candidates)
    review_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path
