"""中文候选票 CSV 输出。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

import pandas as pd

from src.features.required_columns import 基准代码, get_missing_feature_columns, get_required_feature_columns
from src.scoring.scoring_pipeline import score_feature_dataframe_with_failures
from src.utils.chinese import get_chinese_display_name


候选票核心字段 = [
    "排名",
    "代码",
    "中文名称",
    "名称",
    "市场",
    "是否ETF",
    "是否杠杆ETF",
    "最新交易日",
    "最新收盘价",
    "当日涨幅",
    "5日涨幅",
    "10日涨幅",
    "20日涨幅",
    "60日涨幅",
    "成交量",
    "成交额",
    "20日量比",
    "MACD状态",
    "突破状态",
    "相对强度状态",
    "趋势结构分",
    "突破强度分",
    "量能强度分",
    "相对强度分",
    "主升浪形态分",
    "风险扣分",
    "综合评分",
    "等级",
    "等级说明",
    "入选理由",
    "风险标签",
    "评分解释",
    "观察价",
    "失效位",
    "行情数据来源",
    "生成时间",
]

失败清单字段 = ["代码", "失败阶段", "失败原因"]
等级顺序 = {"D": 0, "C": 1, "B": 2, "A": 3, "A+": 4}
杠杆关键词 = [
    "2X",
    "3X",
    "2倍",
    "3倍",
    "LEVERAGED",
    "ULTRA",
    "BULL",
    "BEAR",
    "DAILY TARGET",
    "DIREXION",
    "PROSHARES ULTRA",
]


@dataclass(frozen=True)
class CandidateGenerationResult:
    """候选票生成结果。"""

    candidates: pd.DataFrame
    failures: pd.DataFrame
    metadata_warning: str | None
    cache_file_count: int
    attempted_count: int
    qqq_exists: bool
    spy_exists: bool
    used_score_sample: bool
    include_benchmark: bool


def 保存候选票_csv(df: pd.DataFrame, path: Path | str) -> Path:
    """保存中文候选票 CSV。"""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def 保存失败清单(df: pd.DataFrame, path: Path | str) -> Path:
    """保存候选票失败清单。"""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if df.empty:
        df = pd.DataFrame(columns=失败清单字段)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def 读取股票池元数据(stock_pool_path: Path | str) -> tuple[pd.DataFrame, str | None]:
    """读取股票池元数据，缺失时返回空表和中文提示。"""
    path = Path(stock_pool_path)
    if not path.exists():
        columns = ["代码", "名称", "市场", "是否ETF", "是否杠杆ETF"]
        return pd.DataFrame(columns=columns), f"股票池元数据不存在：{path}"

    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception as exc:
        columns = ["代码", "名称", "市场", "是否ETF", "是否杠杆ETF"]
        return pd.DataFrame(columns=columns), f"股票池元数据读取失败：{exc}"

    for column in ["代码", "名称", "市场", "是否ETF"]:
        if column not in df.columns:
            df[column] = "不足数据"
    df["代码"] = df["代码"].astype(str).str.upper()
    df["是否杠杆ETF"] = df.apply(_识别杠杆ETF, axis=1)
    return df[["代码", "名称", "市场", "是否ETF", "是否杠杆ETF"]].drop_duplicates("代码"), None


def _识别杠杆ETF(row: pd.Series) -> str:
    """根据名称和代码粗略识别杠杆 ETF。"""
    text = f"{row.get('代码', '')} {row.get('名称', '')}".upper()
    if not text.strip():
        return "不足数据"
    return "是" if any(keyword in text for keyword in 杠杆关键词) else "否"


def 合并候选元数据(scored: pd.DataFrame, metadata: pd.DataFrame, generate_time: str) -> pd.DataFrame:
    """把评分结果、技术字段和股票池元数据合并为候选票字段。"""
    output = scored.copy()
    source_defaults = {
        "日期": "",
        "收盘价": pd.NA,
        "当日涨幅": pd.NA,
        "5日涨幅": pd.NA,
        "10日涨幅": pd.NA,
        "20日涨幅": pd.NA,
        "60日涨幅": pd.NA,
        "成交量": pd.NA,
        "成交额": pd.NA,
        "20日量比": pd.NA,
        "MACD状态": "不足数据",
        "突破状态": "不足数据",
        "相对强度状态": "不足数据",
        "趋势结构分": 0,
        "突破强度分": 0,
        "量能强度分": 0,
        "相对强度分": 0,
        "主升浪形态分": 0,
        "风险扣分": 0,
        "综合评分": 0,
        "等级": "D",
        "等级说明": "不符合风格",
        "入选理由": "未触发明显主升浪特征",
        "风险标签": "无明显风险",
        "评分解释": "评分输入不足。",
        "观察价": pd.NA,
        "失效位": pd.NA,
        "数据来源": "不足数据",
    }
    for column, default_value in source_defaults.items():
        if column not in output.columns:
            output[column] = default_value

    if not metadata.empty:
        output = output.merge(metadata, on="代码", how="left")
    else:
        for column in ["名称", "市场", "是否ETF", "是否杠杆ETF"]:
            output[column] = "不足数据"
    for column in ["名称", "市场", "是否ETF", "是否杠杆ETF"]:
        if column not in output.columns:
            output[column] = "不足数据"
        output[column] = output[column].fillna("不足数据")

    output["中文名称"] = output.apply(
        lambda row: get_chinese_display_name(row.get("代码", ""), row.get("名称", ""), row.get("是否ETF", "")),
        axis=1,
    )
    output["最新交易日"] = output["日期"]
    output["最新收盘价"] = output["收盘价"]
    output["行情数据来源"] = output.get("数据来源", "不足数据")
    output["生成时间"] = generate_time
    output = output[候选票核心字段]
    return 格式化候选票数值(output)


def 格式化候选票数值(df: pd.DataFrame) -> pd.DataFrame:
    """对价格和分数做轻量数值格式化，保持数值型。"""
    output = df.copy()
    price_columns = ["最新收盘价", "观察价", "失效位"]
    score_columns = ["趋势结构分", "突破强度分", "量能强度分", "相对强度分", "主升浪形态分", "风险扣分", "综合评分"]
    for column in price_columns:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce").round(4)
    for column in score_columns:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce").round(1)
    return output


def 过滤候选(df: pd.DataFrame, top: int, min_score: float, min_grade: str) -> pd.DataFrame:
    """按 top、最低分和最低等级过滤候选票。"""
    output = df.copy()
    output = output[output["综合评分"] >= min_score]
    min_grade_rank = 等级顺序[min_grade]
    output = output[output["等级"].map(等级顺序).fillna(-1) >= min_grade_rank]
    output = output.sort_values(["综合评分", "代码"], ascending=[False, True]).reset_index(drop=True)
    if top > 0:
        output = output.head(top).copy()
    output["排名"] = range(1, len(output) + 1)
    return output


def 从评分样例生成候选(
    score_sample_path: Path | str,
    stock_pool_path: Path | str,
    top: int,
    min_score: float,
    min_grade: str,
    include_benchmark: bool,
) -> CandidateGenerationResult:
    """从评分样例生成候选票，用于调试。"""
    score_df = pd.read_csv(score_sample_path, encoding="utf-8-sig")
    if not include_benchmark:
        score_df = score_df[~score_df["代码"].astype(str).str.upper().isin(基准代码)].copy()
    metadata, warning = 读取股票池元数据(stock_pool_path)
    generate_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    candidates = 合并候选元数据(score_df, metadata, generate_time)
    candidates = 过滤候选(candidates, top=top, min_score=min_score, min_grade=min_grade)
    return CandidateGenerationResult(
        candidates=candidates,
        failures=pd.DataFrame(columns=失败清单字段),
        metadata_warning=warning,
        cache_file_count=0,
        attempted_count=len(score_df),
        qqq_exists=False,
        spy_exists=False,
        used_score_sample=True,
        include_benchmark=include_benchmark,
    )


def 生成候选票(
    cache_dir: Path | str,
    stock_pool_path: Path | str,
    top: int = 100,
    min_score: float = 0,
    min_grade: str = "D",
    include_benchmark: bool = False,
) -> CandidateGenerationResult:
    """基于缓存行情重新计算特征和评分，生成候选票。"""
    from scripts.生成技术特征样例 import 计算单票特征

    cache_dir = Path(cache_dir)
    files = sorted(cache_dir.glob("*.csv")) if cache_dir.exists() else []
    qqq_path = cache_dir / "QQQ.csv"
    spy_path = cache_dir / "SPY.csv"
    qqq_exists = qqq_path.exists()
    spy_exists = spy_path.exists()
    failures: list[dict[str, str]] = []
    rows: list[pd.DataFrame] = []

    if not qqq_exists:
        failures.append({"代码": "QQQ", "失败阶段": "读取行情", "失败原因": "缺少 QQQ 基准缓存。"})
    if not spy_exists:
        failures.append({"代码": "SPY", "失败阶段": "读取行情", "失败原因": "缺少 SPY 基准缓存。"})
    if not qqq_exists or not spy_exists:
        return CandidateGenerationResult(
            candidates=pd.DataFrame(columns=候选票核心字段),
            failures=pd.DataFrame(failures, columns=失败清单字段),
            metadata_warning=None,
            cache_file_count=len(files),
            attempted_count=0,
            qqq_exists=qqq_exists,
            spy_exists=spy_exists,
            used_score_sample=False,
            include_benchmark=include_benchmark,
        )

    qqq = pd.read_csv(qqq_path, encoding="utf-8-sig")
    spy = pd.read_csv(spy_path, encoding="utf-8-sig")
    required_columns = get_required_feature_columns()
    tickers = [path for path in files if include_benchmark or path.stem.upper() not in set(基准代码)]

    for path in tickers:
        ticker = path.stem.upper()
        try:
            daily = pd.read_csv(path, encoding="utf-8-sig")
        except Exception as exc:
            failures.append({"代码": ticker, "失败阶段": "读取行情", "失败原因": str(exc)})
            continue
        try:
            features = 计算单票特征(daily, qqq, spy)
            missing = get_missing_feature_columns(features.columns.tolist())
            if missing:
                raise ValueError(f"技术特征缺失：{'、'.join(missing)}")
            rows.append(features.tail(1)[required_columns])
        except Exception as exc:
            failures.append({"代码": ticker, "失败阶段": "计算特征", "失败原因": str(exc)})

    if rows:
        feature_df = pd.concat(rows, ignore_index=True)
        scoring_result = score_feature_dataframe_with_failures(feature_df)
        scored = scoring_result.scored.merge(
            feature_df[["代码", "成交量", "20日量比", "MACD状态", "突破状态", "相对强度状态", "数据来源"]],
            on="代码",
            how="left",
        )
        for _, row in scoring_result.failures.iterrows():
            failures.append({"代码": row.get("代码", ""), "失败阶段": "计算评分", "失败原因": row.get("失败原因", "")})
    else:
        scored = pd.DataFrame()

    metadata, warning = 读取股票池元数据(stock_pool_path)
    generate_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if scored.empty:
        candidates = pd.DataFrame(columns=候选票核心字段)
    else:
        candidates = 合并候选元数据(scored, metadata, generate_time)
        candidates = 过滤候选(candidates, top=top, min_score=min_score, min_grade=min_grade)

    return CandidateGenerationResult(
        candidates=candidates,
        failures=pd.DataFrame(failures, columns=失败清单字段),
        metadata_warning=warning,
        cache_file_count=len(files),
        attempted_count=len(tickers),
        qqq_exists=qqq_exists,
        spy_exists=spy_exists,
        used_score_sample=False,
        include_benchmark=include_benchmark,
    )
