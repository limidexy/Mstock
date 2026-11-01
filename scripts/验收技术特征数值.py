"""技术特征数值合理性验收。

只读取本地样例和本地行情缓存，不联网、不下载行情、不实现评分。
"""

from __future__ import annotations

from datetime import datetime
import math
import sys
from pathlib import Path

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from src.features.required_columns import (  # noqa: E402
    REQUIRED_SAMPLE_OUTPUT_COLUMNS,
    合法MACD状态,
    合法突破状态,
    合法量能状态,
    合法风险标签,
    合法是否字段取值,
    合法相对强度状态,
    get_missing_feature_columns,
)
from src.utils.logger import get_logger  # noqa: E402


样例路径 = 项目根目录 / "data" / "output" / "技术特征样例.csv"
报告路径 = 项目根目录 / "data" / "output" / "技术特征数值验收报告.md"
缓存目录 = 项目根目录 / "data" / "cache" / "daily"
容差 = 1e-6


def _to_numeric(series: pd.Series) -> pd.Series:
    """转换为数值序列。"""
    return pd.to_numeric(series, errors="coerce")


def _is_close(left: float, right: float, tolerance: float = 容差) -> bool:
    """判断浮点数是否接近。"""
    if pd.isna(left) and pd.isna(right):
        return True
    if pd.isna(left) or pd.isna(right):
        return False
    return math.isclose(float(left), float(right), rel_tol=1e-6, abs_tol=tolerance)


def _记录异常(anomalies: list[str], message: str) -> None:
    """记录异常样本。"""
    anomalies.append(message)


def 执行验收() -> tuple[bool, dict[str, object]]:
    """执行数值合理性验收并返回是否建议进入下一步。"""
    anomalies: list[str] = []
    serious_issues: list[str] = []

    if not 样例路径.exists():
        serious_issues.append(f"样例文件不存在：{样例路径}")
        sample = pd.DataFrame()
    else:
        sample = pd.read_csv(样例路径, encoding="utf-8-sig")

    row_count = len(sample)
    column_count = len(sample.columns)
    missing_columns = get_missing_feature_columns(sample.columns.tolist()) if not sample.empty else list(REQUIRED_SAMPLE_OUTPUT_COLUMNS)
    if row_count <= 0:
        serious_issues.append("样例文件没有数据行。")
    if missing_columns:
        serious_issues.append(f"缺失必要字段：{'、'.join(missing_columns)}")

    includes_benchmark = False
    duplicate_codes = []
    date_parse_ok = True
    full_empty_core_columns: list[str] = []

    if not sample.empty:
        includes_benchmark = sample["代码"].astype(str).str.upper().isin(["QQQ", "SPY"]).any()
        if includes_benchmark:
            serious_issues.append("样例默认仍包含 QQQ 或 SPY。")

        duplicate_codes = sample.loc[sample["代码"].duplicated(), "代码"].astype(str).tolist()
        if duplicate_codes:
            _记录异常(anomalies, f"存在重复代码：{'、'.join(duplicate_codes)}")

        parsed_dates = pd.to_datetime(sample["日期"], errors="coerce")
        date_parse_ok = not parsed_dates.isna().any()
        if not date_parse_ok:
            serious_issues.append("存在无法解析的日期。")

        core_columns = ["收盘价", "成交量", "成交额", "DIF", "DEA", "MACD柱", "MA5乖离", "当日收盘位置", "风险标签"]
        for column in core_columns:
            if column in sample.columns and sample[column].isna().all():
                full_empty_core_columns.append(column)
        if full_empty_core_columns:
            _记录异常(anomalies, f"存在整列全空核心字段：{'、'.join(full_empty_core_columns)}")

    range_ok = _检查数值范围(sample, anomalies, serious_issues) if not sample.empty else False
    enum_ok = _检查中文枚举(sample, anomalies, serious_issues) if not sample.empty else False
    bool_ok = _检查是否字段(sample, anomalies, serious_issues) if not sample.empty else False
    risk_ok = _检查风险标签(sample, anomalies, serious_issues) if not sample.empty else False
    formula_ok = _抽样复核公式(sample, anomalies, serious_issues) if not sample.empty else False

    recommended = not serious_issues
    context = {
        "样例行数": row_count,
        "样例字段数": column_count,
        "是否排除基准": not includes_benchmark,
        "缺失字段": missing_columns,
        "重复代码": duplicate_codes,
        "日期解析正常": date_parse_ok,
        "整列全空核心字段": full_empty_core_columns,
        "数值范围检查通过": range_ok,
        "中文枚举检查通过": enum_ok,
        "布尔字段检查通过": bool_ok,
        "风险标签检查通过": risk_ok,
        "关键公式检查通过": formula_ok,
        "异常样本": anomalies,
        "严重问题": serious_issues,
        "是否建议进入第8步": recommended,
    }
    _生成报告(context)
    return recommended, context


def _检查数值范围(sample: pd.DataFrame, anomalies: list[str], serious_issues: list[str]) -> bool:
    """检查数值范围。"""
    ok = True
    price_rules = [
        ("开盘价", sample["开盘价"] > 0, True),
        ("最高价", sample["最高价"] > 0, True),
        ("最低价", sample["最低价"] > 0, True),
        ("收盘价", sample["收盘价"] > 0, True),
        ("成交量", sample["成交量"] >= 0, True),
        ("成交额", sample["成交额"] >= 0, True),
        ("最高价>=最低价", sample["最高价"] >= sample["最低价"], True),
        ("最高价>=开盘价", sample["最高价"] >= sample["开盘价"], True),
        ("最高价>=收盘价", sample["最高价"] >= sample["收盘价"], True),
        ("最低价<=开盘价", sample["最低价"] <= sample["开盘价"], True),
        ("最低价<=收盘价", sample["最低价"] <= sample["收盘价"], True),
    ]
    for name, condition, serious in price_rules:
        bad_codes = sample.loc[~condition.fillna(False), "代码"].astype(str).tolist()
        if bad_codes:
            ok = False
            message = f"{name} 检查异常：{'、'.join(bad_codes)}"
            _记录异常(anomalies, message)
            if serious:
                serious_issues.append(message)

    for column in ["当日涨幅", "3日涨幅", "5日涨幅", "10日涨幅", "20日涨幅", "60日涨幅"]:
        values = _to_numeric(sample[column])
        bad = sample.loc[values.notna() & ((values < -1) | (values > 10)), "代码"].astype(str).tolist()
        if bad:
            _记录异常(anomalies, f"{column} 超出常规范围：{'、'.join(bad)}")

    for column in ["MA5乖离", "MA10乖离", "MA20乖离", "MA30乖离", "MA50乖离", "MA60乖离"]:
        values = _to_numeric(sample[column])
        bad = sample.loc[values.notna() & ((values < -1) | (values > 10)), "代码"].astype(str).tolist()
        if bad:
            _记录异常(anomalies, f"{column} 超出常规范围：{'、'.join(bad)}")

    for column in ["20日量比", "成交额放大倍数"]:
        values = _to_numeric(sample[column])
        negative = sample.loc[values.notna() & (values < 0), "代码"].astype(str).tolist()
        too_large = sample.loc[values.notna() & (values > 50), "代码"].astype(str).tolist()
        if negative:
            ok = False
            message = f"{column} 出现负数：{'、'.join(negative)}"
            _记录异常(anomalies, message)
            serious_issues.append(message)
        if too_large:
            _记录异常(anomalies, f"{column} 大于50：{'、'.join(too_large)}")

    close_position = _to_numeric(sample["当日收盘位置"])
    bad_position = sample.loc[close_position.notna() & ((close_position < 0) | (close_position > 1)), "代码"].astype(str).tolist()
    if bad_position:
        ok = False
        message = f"当日收盘位置超出0到1：{'、'.join(bad_position)}"
        _记录异常(anomalies, message)
        serious_issues.append(message)

    for column in ["距离20日新高", "距离60日新高", "距离120日新高"]:
        values = _to_numeric(sample[column])
        bad = sample.loc[values.notna() & (values < -1), "代码"].astype(str).tolist()
        if bad:
            _记录异常(anomalies, f"{column} 小于-1：{'、'.join(bad)}")

    volatility = _to_numeric(sample["20日波动率"])
    bad_volatility = sample.loc[volatility.notna() & (volatility < 0), "代码"].astype(str).tolist()
    if bad_volatility:
        ok = False
        message = f"20日波动率出现负数：{'、'.join(bad_volatility)}"
        _记录异常(anomalies, message)
        serious_issues.append(message)

    drawdown = _to_numeric(sample["60日回撤"])
    positive_drawdown = sample.loc[drawdown.notna() & (drawdown > 1e-10), "代码"].astype(str).tolist()
    if positive_drawdown:
        ok = False
        message = f"60日回撤大于0，疑似定义错误：{'、'.join(positive_drawdown)}"
        _记录异常(anomalies, message)
        serious_issues.append(message)

    return ok


def _检查中文枚举(sample: pd.DataFrame, anomalies: list[str], serious_issues: list[str]) -> bool:
    """检查中文枚举是否合法。"""
    enum_rules = {
        "MACD状态": set(合法MACD状态),
        "量能状态": set(合法量能状态),
        "突破状态": set(合法突破状态),
        "相对强度状态": set(合法相对强度状态),
    }
    ok = True
    for column, allowed in enum_rules.items():
        invalid = sorted(set(sample[column].dropna().astype(str)) - allowed)
        if invalid:
            ok = False
            message = f"{column} 存在非法枚举：{'、'.join(invalid)}"
            _记录异常(anomalies, message)
            serious_issues.append(message)
    return ok


def _检查是否字段(sample: pd.DataFrame, anomalies: list[str], serious_issues: list[str]) -> bool:
    """检查所有是否字段取值统一。"""
    ok = True
    allowed = set(合法是否字段取值)
    bool_columns = [column for column in sample.columns if column.startswith("是否")]
    for column in bool_columns:
        values = set(sample[column].dropna().astype(str))
        if not values or "" in values:
            ok = False
            message = f"{column} 存在空值。"
            _记录异常(anomalies, message)
            serious_issues.append(message)
            continue
        if not values <= allowed:
            ok = False
            message = f"{column} 取值不统一或非法：{'、'.join(sorted(values))}"
            _记录异常(anomalies, message)
            serious_issues.append(message)
    return ok


def _检查风险标签(sample: pd.DataFrame, anomalies: list[str], serious_issues: list[str]) -> bool:
    """检查风险标签规范。"""
    ok = True
    allowed = set(合法风险标签)
    invalid_rows = []
    empty_rows = []
    for _, row in sample.iterrows():
        code = str(row["代码"])
        value = str(row.get("风险标签", "")).strip()
        if value in {"", "无", "None", "nan", "NaN"}:
            empty_rows.append(code)
            continue
        tags = [tag.strip() for tag in value.replace(";", "；").split("；") if tag.strip()]
        invalid = [tag for tag in tags if tag not in allowed]
        if invalid:
            invalid_rows.append(f"{code}:{'、'.join(invalid)}")
    if empty_rows:
        ok = False
        message = f"风险标签为空或旧值：{'、'.join(empty_rows)}"
        _记录异常(anomalies, message)
        serious_issues.append(message)
    if invalid_rows:
        ok = False
        message = f"风险标签存在非法值：{'；'.join(invalid_rows)}"
        _记录异常(anomalies, message)
        serious_issues.append(message)
    return ok


def _抽样复核公式(sample: pd.DataFrame, anomalies: list[str], serious_issues: list[str]) -> bool:
    """抽样复核核心公式。"""
    ok = True
    sample_rows = sample.head(5)
    for _, row in sample_rows.iterrows():
        code = str(row["代码"])
        checks = [
            ("成交额", row["成交额"], row["收盘价"] * row["成交量"], True),
            ("20日量比", row["20日量比"], row["成交量"] / row["MAVOL20"] if row["MAVOL20"] else float("nan"), False),
            ("MACD柱", row["MACD柱"], 2 * (row["DIF"] - row["DEA"]), True),
            ("MA5乖离", row["MA5乖离"], row["收盘价"] / row["MA5"] - 1 if row["MA5"] else float("nan"), True),
            (
                "当日收盘位置",
                row["当日收盘位置"],
                0.5 if row["最高价"] == row["最低价"] else (row["收盘价"] - row["最低价"]) / (row["最高价"] - row["最低价"]),
                True,
            ),
        ]
        for name, actual, expected, serious in checks:
            if pd.notna(expected) and not _is_close(actual, expected, tolerance=1e-5):
                ok = False
                message = f"{code} {name} 公式不一致：实际 {actual}，期望 {expected}"
                _记录异常(anomalies, message)
                if serious:
                    serious_issues.append(message)

        cache_path = 缓存目录 / f"{code}.csv"
        if cache_path.exists():
            daily = pd.read_csv(cache_path, encoding="utf-8-sig")
            daily["日期"] = pd.to_datetime(daily["日期"])
            daily = daily.sort_values("日期").reset_index(drop=True)
            daily["最高价"] = _to_numeric(daily["最高价"])
            daily["收盘价"] = _to_numeric(daily["收盘价"])
            if len(daily) >= 21:
                previous_20_high = daily["最高价"].rolling(window=20, min_periods=20).max().shift(1).iloc[-1]
                expected_distance = row["收盘价"] / previous_20_high - 1
                if pd.notna(previous_20_high) and not _is_close(row["距离20日新高"], expected_distance, tolerance=1e-5):
                    ok = False
                    message = f"{code} 距离20日新高公式不一致：实际 {row['距离20日新高']}，期望 {expected_distance}"
                    _记录异常(anomalies, message)
            if len(daily) >= 20:
                highest_close_60 = daily["收盘价"].rolling(window=60, min_periods=20).max().iloc[-1]
                expected_drawdown = row["收盘价"] / highest_close_60 - 1
                if pd.notna(highest_close_60) and not _is_close(row["60日回撤"], expected_drawdown, tolerance=1e-5):
                    ok = False
                    message = f"{code} 60日回撤公式不一致：实际 {row['60日回撤']}，期望 {expected_drawdown}"
                    _记录异常(anomalies, message)
                    serious_issues.append(message)
    return ok


def _生成报告(context: dict[str, object]) -> None:
    """生成中文验收报告。"""
    recommended_text = "可以进入第 8 步评分系统" if context["是否建议进入第8步"] else "不建议进入第 8 步评分系统"
    anomalies = context["异常样本"] or ["无"]
    serious = context["严重问题"] or ["无"]
    lines = [
        "# 技术特征数值验收报告",
        "",
        f"1. 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"2. 样例文件路径：`{样例路径}`",
        f"3. 样例行数：{context['样例行数']}",
        f"4. 样例字段数：{context['样例字段数']}",
        f"5. 是否排除 QQQ/SPY：{'是' if context['是否排除基准'] else '否'}",
        f"6. 字段完整性结论：{'通过' if not context['缺失字段'] else '未通过，缺失：' + '、'.join(context['缺失字段'])}",
        f"7. 数值范围检查结论：{'通过' if context['数值范围检查通过'] else '存在异常'}",
        f"8. 中文枚举检查结论：{'通过' if context['中文枚举检查通过'] else '存在异常'}",
        f"9. 布尔字段检查结论：{'通过' if context['布尔字段检查通过'] else '存在异常'}",
        f"10. 风险标签检查结论：{'通过' if context['风险标签检查通过'] else '存在异常'}",
        f"11. 关键公式抽样复核结论：{'通过' if context['关键公式检查通过'] else '存在异常'}",
        "12. 异常样本清单：",
    ]
    for anomaly in anomalies:
        lines.append(f"    - {anomaly}")
    lines.extend(
        [
            "13. 是否建议进入第 8 步评分系统：",
            f"    - {recommended_text}",
            "",
            "## 严重问题",
            "",
        ]
    )
    for item in serious:
        lines.append(f"- {item}")
    报告路径.parent.mkdir(parents=True, exist_ok=True)
    报告路径.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """运行验收。"""
    logger = get_logger("Mstock特征数值验收")
    recommended, context = 执行验收()
    logger.info(f"数值验收报告已生成：{报告路径}")
    logger.info(f"样例行数：{context['样例行数']}，字段数：{context['样例字段数']}")
    logger.info("验收结论：" + ("可以进入第 8 步评分系统" if recommended else "不建议进入第 8 步评分系统"))
    return 0 if recommended else 1


if __name__ == "__main__":
    raise SystemExit(main())
