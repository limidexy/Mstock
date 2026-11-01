"""中文 HTML 报告图表生成。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


图表失败清单字段 = ["代码", "失败阶段", "失败原因"]
候选中文字体 = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans"]


@dataclass(frozen=True)
class ChartGenerationResult:
    """图表生成结果。"""

    ticker: str
    chart_path: Path | None
    success: bool
    failure_reason: str | None = None


def 配置图表字体() -> str | None:
    """配置 matplotlib 中文字体，字体缺失时返回提示但不中断。"""
    available_fonts = {font.name for font in matplotlib.font_manager.fontManager.ttflist}
    for font_name in 候选中文字体:
        if font_name in available_fonts:
            plt.rcParams["font.sans-serif"] = [font_name]
            plt.rcParams["axes.unicode_minus"] = False
            return None
    plt.rcParams["axes.unicode_minus"] = False
    return "未检测到常见中文字体，图表可能使用系统默认字体显示中文。"


def 读取行情缓存(cache_dir: Path | str, ticker: str) -> pd.DataFrame:
    """读取单只股票本地日线缓存。"""
    path = Path(cache_dir) / f"{ticker.upper()}.csv"
    if not path.exists():
        raise FileNotFoundError(f"缺少行情缓存文件：{path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    required_columns = ["日期", "收盘价"]
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"行情缓存缺少字段：{'、'.join(missing)}")
    output = df.copy()
    output["日期"] = pd.to_datetime(output["日期"], errors="coerce")
    output["收盘价"] = pd.to_numeric(output["收盘价"], errors="coerce")
    output = output.dropna(subset=["日期", "收盘价"]).sort_values("日期")
    if output.empty:
        raise ValueError("行情缓存没有可用于绘图的有效数据。")
    return output


def 生成单票走势图(
    ticker: str,
    cache_dir: Path | str,
    charts_dir: Path | str,
    days: int = 90,
) -> ChartGenerationResult:
    """生成单只股票最近走势 PNG，包含收盘价、MA5、MA10、MA20。"""
    ticker = str(ticker).upper()
    chart_path = Path(charts_dir) / f"{ticker}.png"
    try:
        配置图表字体()
        daily = 读取行情缓存(cache_dir, ticker).tail(days).copy()
        daily["MA5"] = daily["收盘价"].rolling(5, min_periods=1).mean()
        daily["MA10"] = daily["收盘价"].rolling(10, min_periods=1).mean()
        daily["MA20"] = daily["收盘价"].rolling(20, min_periods=1).mean()

        chart_path.parent.mkdir(parents=True, exist_ok=True)
        figure, axis = plt.subplots(figsize=(7.2, 3.6), dpi=120)
        axis.plot(daily["日期"], daily["收盘价"], label="收盘价", color="#1f2937", linewidth=1.8)
        axis.plot(daily["日期"], daily["MA5"], label="MA5", color="#0f766e", linewidth=1.0)
        axis.plot(daily["日期"], daily["MA10"], label="MA10", color="#2563eb", linewidth=1.0)
        axis.plot(daily["日期"], daily["MA20"], label="MA20", color="#b45309", linewidth=1.0)
        axis.set_title(f"{ticker} 最近{min(days, len(daily))}个交易日走势")
        axis.set_xlabel("日期")
        axis.set_ylabel("价格")
        axis.grid(True, linestyle="--", linewidth=0.5, alpha=0.35)
        axis.legend(loc="best", fontsize=8)
        figure.autofmt_xdate()
        figure.tight_layout()
        figure.savefig(chart_path, format="png")
        plt.close(figure)
        return ChartGenerationResult(ticker=ticker, chart_path=chart_path, success=True)
    except Exception as exc:
        plt.close("all")
        return ChartGenerationResult(ticker=ticker, chart_path=None, success=False, failure_reason=str(exc))


def 批量生成走势图(
    candidates: pd.DataFrame,
    cache_dir: Path | str,
    charts_dir: Path | str,
    days: int = 90,
) -> tuple[dict[str, Path], pd.DataFrame]:
    """为候选票批量生成走势图，单只失败不会中断。"""
    chart_paths: dict[str, Path] = {}
    failures: list[dict[str, str]] = []
    Path(charts_dir).mkdir(parents=True, exist_ok=True)
    for ticker in candidates.get("代码", pd.Series(dtype=str)).astype(str).str.upper():
        result = 生成单票走势图(ticker, cache_dir, charts_dir, days=days)
        if result.success and result.chart_path is not None:
            chart_paths[ticker] = result.chart_path
        else:
            failures.append({"代码": ticker, "失败阶段": "生成图表", "失败原因": result.failure_reason or "未知错误"})
    return chart_paths, pd.DataFrame(failures, columns=图表失败清单字段)
