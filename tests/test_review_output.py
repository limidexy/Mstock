from pathlib import Path

import pandas as pd

from src.reports.csv_report import 候选票核心字段, 生成候选票
from src.reports.review_report import 人工校对字段, 保存待校对_csv, 生成待校对表


项目根目录 = Path(__file__).resolve().parents[1]


def test_review_output_contains_candidate_and_manual_fields():
    """待校对表包含候选票字段和人工校对字段。"""
    result = 生成候选票(
        cache_dir=项目根目录 / "data" / "cache" / "daily",
        stock_pool_path=项目根目录 / "data" / "processed" / "美股股票池.csv",
        top=3,
    )

    review = 生成待校对表(result.candidates, review_date="2026-06-01")

    missing_candidate_fields = [field for field in 候选票核心字段 if field not in review.columns]
    missing_review_fields = [field for field in 人工校对字段 if field not in review.columns]
    assert not missing_candidate_fields
    assert not missing_review_fields
    for column in ["我的校对", "我的备注", "是否加入观察池", "是否实际交易", "交易结果"]:
        assert review[column].eq("").all()
    assert review["复盘日期"].eq("2026-06-01").all()


def test_review_csv_uses_bom_and_keeps_manual_fields_blank(tmp_path):
    """待校对 CSV 使用 utf-8-sig，并保留人工字段为空。"""
    result = 生成候选票(
        cache_dir=项目根目录 / "data" / "cache" / "daily",
        stock_pool_path=项目根目录 / "data" / "processed" / "美股股票池.csv",
        top=3,
    )
    output_path = tmp_path / "待校对.csv"

    保存待校对_csv(result.candidates, output_path)

    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")
    saved = pd.read_csv(output_path, encoding="utf-8-sig", keep_default_na=False)
    for column in ["我的校对", "我的备注", "是否加入观察池", "是否实际交易", "交易结果"]:
        assert saved[column].eq("").all()
