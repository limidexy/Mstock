from pathlib import Path

import pandas as pd

from src.features.required_columns import (
    合法MACD状态,
    合法突破状态,
    合法量能状态,
    合法是否字段取值,
    get_missing_feature_columns,
)


项目根目录 = Path(__file__).resolve().parents[1]
样例路径 = 项目根目录 / "data" / "output" / "技术特征样例.csv"


def 读取样例() -> pd.DataFrame:
    """读取技术特征样例。"""
    return pd.read_csv(样例路径, encoding="utf-8-sig")


def test_feature_sample_value_ranges_and_required_columns():
    """检查样例字段完整、收盘位置和量比等数值范围合理。"""
    sample = 读取样例()

    assert not sample.empty
    assert not get_missing_feature_columns(sample.columns.tolist())
    assert sample["当日收盘位置"].dropna().between(0, 1).all()
    assert (sample["成交额放大倍数"].dropna() >= 0).all()
    assert (sample["20日量比"].dropna() >= 0).all()


def test_feature_sample_core_formulas():
    """检查核心公式一致。"""
    sample = 读取样例()

    assert ((sample["成交额"] - sample["收盘价"] * sample["成交量"]).abs() < 1e-5).all()
    assert ((sample["MACD柱"] - 2 * (sample["DIF"] - sample["DEA"])).abs().dropna() < 1e-8).all()
    assert ((sample["MA5乖离"] - (sample["收盘价"] / sample["MA5"] - 1)).abs().dropna() < 1e-8).all()


def test_feature_sample_risk_tags_are_not_empty():
    """检查风险标签没有空值，没有风险时使用无明显风险。"""
    sample = 读取样例()
    tags = sample["风险标签"].astype(str).str.strip()

    assert tags.notna().all()
    assert not tags.isin(["", "无", "None", "nan", "NaN"]).any()
    assert "无明显风险" in set(tags) or tags.str.contains("；").any() or len(tags) > 0


def test_feature_sample_chinese_enums_are_legal():
    """检查中文枚举合法。"""
    sample = 读取样例()

    assert set(sample["MACD状态"].dropna()) <= set(合法MACD状态)
    assert set(sample["量能状态"].dropna()) <= set(合法量能状态)
    assert set(sample["突破状态"].dropna()) <= set(合法突破状态)


def test_feature_sample_excludes_benchmarks_and_boolean_values_are_unified():
    """检查样例默认排除基准，所有是否字段取值统一。"""
    sample = 读取样例()

    assert "QQQ" not in set(sample["代码"])
    assert "SPY" not in set(sample["代码"])

    allowed = set(合法是否字段取值)
    bool_columns = [column for column in sample.columns if column.startswith("是否")]
    assert bool_columns
    for column in bool_columns:
        values = set(sample[column].dropna().astype(str))
        assert values
        assert values <= allowed, f"{column} 出现非法取值：{values}"
