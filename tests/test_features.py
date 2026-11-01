import pandas as pd
import pytest

from src.features.breakout import 添加突破特征
from src.features.macd import 添加MACD特征
from src.features.moving_average import 添加均线特征
from src.features.relative_strength import 添加相对强度特征
from src.features.required_columns import get_missing_feature_columns, get_required_feature_columns
from src.features.risk import 添加风险特征
from src.features.volume import 添加量能特征


def make_daily_data(days: int = 140, ticker: str = "TEST", start_price: float = 10.0) -> pd.DataFrame:
    """生成可重复的日线测试数据。"""
    dates = pd.bdate_range("2026-01-01", periods=days)
    close = [start_price + index * 0.2 for index in range(days)]
    return pd.DataFrame(
        {
            "日期": [item.strftime("%Y-%m-%d") for item in dates],
            "代码": ticker,
            "开盘价": [value - 0.1 for value in close],
            "最高价": [value + 0.2 for value in close],
            "最低价": [value - 0.3 for value in close],
            "收盘价": close,
            "复权收盘价": close,
            "成交量": [1000 + index * 10 for index in range(days)],
            "数据来源": "测试",
        }
    )


def test_moving_average_features_are_chinese_and_sorted():
    """检查均线特征输出中文字段，并按日期升序计算。"""
    df = make_daily_data(130).iloc[::-1].reset_index(drop=True)

    result = 添加均线特征(df)

    assert result["日期"].is_monotonic_increasing
    assert "MA5" in result.columns
    assert "MA30" in result.columns
    assert "MA250" in result.columns
    assert "MA20乖离" in result.columns
    assert "MA60斜率" in result.columns
    assert "是否站上MA60" in result.columns
    assert "是否均线多头排列" in result.columns
    assert "是否短期均线向上发散" in result.columns
    assert "是否主升浪加速" in result.columns
    assert result["是否均线多头排列"].iloc[-1] == "是"


def test_macd_features_include_chinese_status():
    """检查 MACD 特征包含中文状态。"""
    result = 添加MACD特征(make_daily_data(80))

    assert "DIF" in result.columns
    assert "DEA" in result.columns
    assert "MACD柱" in result.columns
    assert "MACD状态" in result.columns
    assert result["MACD状态"].iloc[-1] in {"多头扩大", "多头收缩", "空头扩大", "空头收缩", "金叉", "死叉", "不足数据"}


def test_volume_features_include_amount_and_ratio():
    """检查量能特征包含成交额和20日量比。"""
    result = 添加量能特征(make_daily_data(40))

    assert "成交额" in result.columns
    assert "MAVOL5" in result.columns
    assert "MAVOL10" in result.columns
    assert "MAVOL20" in result.columns
    assert "成交额MA20" in result.columns
    assert "20日量比" in result.columns
    assert "是否放量" in result.columns
    assert "是否明显放量" in result.columns
    assert "是否缩量" in result.columns
    assert "量能状态" in result.columns
    assert pd.notna(result["20日量比"].iloc[-1])


def test_breakout_uses_prior_high_without_future_leakage():
    """检查突破判断使用历史高点，不使用未来高点。"""
    df = make_daily_data(80)
    base = 添加突破特征(df)

    changed = df.copy()
    changed.loc[79, "最高价"] = 9999
    changed_result = 添加突破特征(changed)

    assert base.loc[60, "前20日高点"] == changed_result.loc[60, "前20日高点"]
    assert base.loc[60, "距离20日新高"] == changed_result.loc[60, "距离20日新高"]
    assert "是否突破20日新高" in base.columns
    assert "是否突破120日新高" in base.columns
    assert "距离120日新高" in base.columns
    assert "是否收盘接近日高" in base.columns
    assert "当日收盘位置" in base.columns


def test_relative_strength_features_compare_to_qqq_and_spy():
    """检查相对强度特征相对 QQQ 和 SPY 计算。"""
    target = make_daily_data(90, ticker="TARGET", start_price=10)
    qqq = make_daily_data(90, ticker="QQQ", start_price=20)
    spy = make_daily_data(90, ticker="SPY", start_price=30)

    result = 添加相对强度特征(target, qqq, spy)

    assert "相对QQQ强度" in result.columns
    assert "相对SPY强度" in result.columns
    assert "相对QQQ5日强度" in result.columns
    assert "相对QQQ60日强度" in result.columns
    assert "是否5日强于QQQ" in result.columns
    assert "是否20日强于QQQ" in result.columns
    assert "是否20日强于SPY" in result.columns
    assert "相对强度状态" in result.columns
    assert pd.notna(result["相对QQQ强度"].iloc[-1])


def test_risk_features_generate_chinese_tags():
    """检查风险特征生成中文风险标签。"""
    df = make_daily_data(80)
    df.loc[df.index[-1], "收盘价"] = df.loc[df.index[-1], "收盘价"] * 1.3
    df.loc[df.index[-1], "最高价"] = df.loc[df.index[-1], "收盘价"] * 1.05

    result = 添加风险特征(df)

    assert "20日波动率" in result.columns
    assert "60日回撤" in result.columns
    assert "是否距离MA5过远" in result.columns
    assert "是否距离MA10过远" in result.columns
    assert "是否连续加速过热" in result.columns
    assert "是否长上影线" in result.columns
    assert "是否距离MA20过远" in result.columns
    assert "是否流动性不足" in result.columns
    assert "是否高波动" in result.columns
    assert "是否高波动风险" in result.columns
    assert "风险标签" in result.columns
    assert isinstance(result["风险标签"].iloc[-1], str)


def test_feature_functions_raise_chinese_errors_for_missing_columns():
    """检查缺少必要字段时输出中文错误。"""
    df = pd.DataFrame({"日期": ["2026-01-01"]})

    with pytest.raises(ValueError, match="缺少字段"):
        添加均线特征(df)

    with pytest.raises(ValueError, match="缺少字段"):
        添加量能特征(pd.DataFrame({"日期": ["2026-01-01"], "收盘价": [10.0]}))


def test_required_feature_columns_are_complete_after_pipeline():
    """检查完整特征流水线包含统一字段清单。"""
    target = make_daily_data(280, ticker="TARGET", start_price=10)
    qqq = make_daily_data(280, ticker="QQQ", start_price=20)
    spy = make_daily_data(280, ticker="SPY", start_price=30)

    result = 添加均线特征(target)
    result = 添加MACD特征(result)
    result = 添加量能特征(result)
    result = 添加突破特征(result)
    result = 添加风险特征(result)
    result = 添加相对强度特征(result, qqq, spy)

    missing = get_missing_feature_columns(result.columns.tolist())

    assert not missing
    assert len(get_required_feature_columns()) >= 80
