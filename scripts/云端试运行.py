"""在独立临时目录完成小批量公开行情到中文报告的云端试运行。"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from html import escape
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from scripts.更新行情数据 import 创建数据源
from src.data.cache import 批量更新日线缓存
from src.reports.csv_report import 保存候选票_csv, 保存失败清单, 生成候选票
from src.reports.html_report import 生成HTML报告
from src.reports.review_report import 保存待校对_csv
from src.utils.logger import get_logger

默认试运行代码 = "AA,AAPL,NBIS,MSFT,NVDA,AMD,TSLA,META"
基准代码 = ("QQQ", "SPY")
数据检查字段 = ["代码", "状态", "最新交易日", "有效行数", "数据来源", "输入SHA256", "说明"]


def 解析试运行代码(text: str) -> list[str]:
    """限制请求规模并拒绝路径或命令内容，基准单独添加。"""
    tickers = list(dict.fromkeys(x.strip().upper() for x in text.split(",") if x.strip()))
    if not tickers or len(tickers) > 30:
        raise ValueError("请指定1到30只标的，QQQ和SPY基准不计入候选。")
    if any(not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", ticker) for ticker in tickers):
        raise ValueError("代码只能包含英文字母、数字、点或连字符。")
    tickers = [ticker for ticker in tickers if ticker not in 基准代码]
    if not tickers:
        raise ValueError("除QQQ和SPY外，至少指定一只需要评分的标的。")
    return tickers


def 获取已收盘日期上限(now: datetime) -> pd.Timestamp:
    """以纽约17点为保守完成界限，不把当日盘中日线当成完整日线。"""
    if now.tzinfo is None:
        raise ValueError("运行时间必须包含时区。")
    local = now.astimezone(ZoneInfo("America/New_York"))
    cutoff = local.date() if local.hour >= 17 else local.date() - timedelta(days=1)
    return pd.Timestamp(cutoff)


def 校验完整日线(frame: pd.DataFrame, ticker: str, cutoff: pd.Timestamp) -> pd.DataFrame:
    """拒绝损坏日线，去掉尚未完成的交易日，要求足够的指标历史。"""
    required = ["日期", "代码", "开盘价", "最高价", "最低价", "收盘价", "复权收盘价", "成交量", "数据来源"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"日线缺少字段：{'、'.join(missing)}")
    data = frame.copy()
    dates = pd.to_datetime(data["日期"], errors="coerce")
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError("日期无效或包含重复交易日。")
    if not data["代码"].astype(str).str.upper().eq(ticker).all():
        raise ValueError("缓存中的代码与请求代码不一致。")
    data["日期"] = dates.dt.strftime("%Y-%m-%d")
    data = data.loc[dates <= cutoff].sort_values("日期").reset_index(drop=True)
    if len(data) < 130:
        raise ValueError(f"完整日线只有{len(data)}行，不足130行。")
    prices = data[["开盘价", "最高价", "最低价", "收盘价", "复权收盘价"]].apply(pd.to_numeric, errors="coerce")
    volume = pd.to_numeric(data["成交量"], errors="coerce")
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("存在缺失、非有限数值或零负价格。")
    if not np.isfinite(volume.to_numpy()).all() or (volume < 0).any():
        raise ValueError("存在无效或负成交量。")
    tolerance = prices["最高价"].abs() * 1e-6
    if ((prices["最高价"] + tolerance < prices[["开盘价", "收盘价", "最低价"]].max(axis=1))
            | (prices["最低价"] - tolerance > prices[["开盘价", "收盘价"]].min(axis=1))).any():
        raise ValueError("开高低收关系异常。")
    data[prices.columns] = prices
    data["成交量"] = volume
    if data["数据来源"].isna().any() or data["数据来源"].astype(str).str.strip().eq("").any():
        raise ValueError("行情缺少数据来源。")
    return data


def 确定基准日期(frames: dict[str, pd.DataFrame], cutoff: pd.Timestamp) -> str:
    """两个基准必须同日且足够新，避免把旧缓存当成当前运行结果。"""
    if any(ticker not in frames for ticker in 基准代码):
        raise ValueError("QQQ或SPY基准下载或数据检查失败，停止评分。")
    dates = [str(frames[ticker]["日期"].iloc[-1]) for ticker in 基准代码]
    if dates[0] != dates[1]:
        raise ValueError("QQQ与SPY最新完整交易日不一致，停止评分。")
    if (cutoff - pd.Timestamp(dates[0])).days > 7:
        raise ValueError("基准日线已超过七个自然日，停止生成当前候选。")
    return dates[0]


def 保存运行说明(output: Path, summary: dict) -> None:
    """保存中文结果和可追溯元数据，失败也明确记录。"""
    (output / "运行摘要.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Mstock 云端小批量试运行",
        "",
        f"- 运行状态：{summary['运行状态']}",
        f"- 获取时间：{summary['获取时间']}",
        f"- 源码版本：{summary['源码版本']}",
        f"- 行情基准日期：{summary.get('行情基准日期', '未确认')}",
        f"- 请求股票：{'、'.join(summary['请求股票'])}；另取QQQ和SPY基准。",
        f"- 下载成功：{summary.get('下载成功数量', 0)}；下载失败：{summary.get('下载失败数量', 0)}。",
        f"- 评分输出：{summary.get('评分输出数量', 0)}；B级及以上：{summary.get('B级及以上数量', 0)}。",
        f"- 图表生成：{summary.get('图表数量', 0)}。",
        "- 本次仅验证指定小批量，不代表全市场覆盖、热度榜筛选或自动推荐。",
        "- 排名保留原有全部等级；低等级记录不代表符合主升浪风格。",
        "- 本次不自动交易；未恢复旧电脑人工校对、历史报告和原始备份。",
        "- 行情原始缓存仅用于本轮计算，不包含在公开仓库提交或报告附件中。",
        "- 原有评分公式、权重和等级阈值保持原样。",
        "",
    ]
    if summary.get("失败原因"):
        lines.extend(["## 失败原因", "", summary["失败原因"], ""])
    (output / "运行说明.md").write_text("\n".join(lines), encoding="utf-8")


def 运行云端试运行(
    *, tickers: str, output_dir: Path | str, allow_network: bool = False,
    now: datetime | None = None, days: int = 300,
) -> dict:
    """显式授权后执行，所有下载与中间数据在独立临时目录。"""
    if not allow_network:
        raise PermissionError("尚未允许联网，请显式确认后使用--allow-network。")
    requested = 解析试运行代码(tickers)
    if not 130 <= days <= 1000:
        raise ValueError("日线数量应在130到1000之间。")
    current = now or datetime.now(timezone.utc)
    cutoff = 获取已收盘日期上限(current)
    output = Path(output_dir).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError("报告目标目录不是空目录，请更换目录，禁止覆盖已有结果。")
    output.mkdir(parents=True, exist_ok=True)
    import os
    summary = {
        "运行状态": "进行中",
        "获取时间": current.astimezone(ZoneInfo("Asia/Singapore")).isoformat(),
        "源码版本": os.getenv("GITHUB_SHA", "本地运行，未提供提交版本"),
        "请求股票": requested,
        "数据频率": "日线",
        "完整日线上限": cutoff.strftime("%Y-%m-%d"),
        "原始缓存位置": "仅保留在本轮独立临时目录，结束后清理",
    }
    logger = get_logger("Mstock云端试运行")
    checks: list[dict] = []
    try:
        with tempfile.TemporaryDirectory(prefix="Mstock-cloud-") as temporary:
            work = Path(temporary)
            provider = 创建数据源("auto")
            result = 批量更新日线缓存(
                provider, list(基准代码) + requested, cache_dir=work / "cache",
                days=days, force=False, max_retries=1, sleep_min=1.0, sleep_max=3.0,
                failure_path=output / "下载失败清单.csv", logger=logger,
            )
            summary.update(下载成功数量=result.成功数量, 下载失败数量=result.失败数量)
            frames: dict[str, pd.DataFrame] = {}
            for ticker in list(基准代码) + requested:
                path = work / "cache" / "daily" / f"{ticker}.csv"
                record = dict.fromkeys(数据检查字段, "")
                record.update(代码=ticker, 状态="不可用")
                try:
                    raw_bytes = path.read_bytes()
                    record["输入SHA256"] = hashlib.sha256(raw_bytes).hexdigest()
                    frame = 校验完整日线(pd.read_csv(path, encoding="utf-8-sig"), ticker, cutoff)
                    frames[ticker] = frame
                    record.update(状态="数据检查通过", 最新交易日=frame["日期"].iloc[-1],
                                  有效行数=len(frame), 数据来源="、".join(sorted(set(frame["数据来源"].astype(str)))))
                except Exception as exc:
                    record["说明"] = str(exc) if path.exists() else "本轮未获得行情，请查看下载失败清单。"
                checks.append(record)
            pd.DataFrame(checks, columns=数据检查字段).to_csv(output / "数据检查.csv", index=False, encoding="utf-8-sig")
            asof = 确定基准日期(frames, cutoff)
            summary["行情基准日期"] = asof
            selected = [ticker for ticker in requested
                        if ticker in frames and str(frames[ticker]["日期"].iloc[-1]) == asof]
            for record in checks:
                if record["代码"] in requested:
                    record["状态"] = "参与评分" if record["代码"] in selected else "排除"
                    if record["代码"] in frames and record["代码"] not in selected:
                        record["说明"] = "最新完整日线未与QQQ和SPY基准对齐。"
            pd.DataFrame(checks, columns=数据检查字段).to_csv(output / "数据检查.csv", index=False, encoding="utf-8-sig")
            if not selected:
                raise ValueError("没有与基准日期对齐的有效股票，未生成候选报告。")
            eligible = work / "aligned"
            eligible.mkdir()
            for ticker in list(基准代码) + selected:
                frames[ticker].to_csv(eligible / f"{ticker}.csv", index=False, encoding="utf-8-sig")
            pool = work / "本轮指定池.csv"
            pd.DataFrame([{
                "代码": ticker, "名称": f"本轮指定标的{ticker}", "市场": "美股",
                "是否ETF": "是" if ticker in 基准代码 else "待核实", "是否测试证券": "否",
            } for ticker in list(基准代码) + selected]).to_csv(pool, index=False, encoding="utf-8-sig")
            scored = 生成候选票(eligible, pool, top=len(selected), include_benchmark=False)
            if scored.candidates.empty or not scored.failures.empty:
                保存失败清单(scored.failures, output / "计算失败清单.csv")
                raise ValueError("特征或评分生成失败，请查看计算失败清单。")
            candidates = scored.candidates
            if not candidates["最新交易日"].astype(str).eq(asof).all():
                raise ValueError("候选日期与行情基准日期不一致。")
            scores = pd.to_numeric(candidates["综合评分"], errors="coerce")
            if not scores.between(0, 100).all() or not scores.is_monotonic_decreasing:
                raise ValueError("评分无效或排序异常。")
            保存候选票_csv(candidates, output / "候选票.csv")
            保存待校对_csv(candidates, output / "空白待校对.csv")
            report = 生成HTML报告(
                input_path=output / "候选票.csv", cache_dir=eligible,
                output_path=output / "index.html", charts_dir=output / "charts",
                report_path=output / "HTML验收说明.md", failure_path=output / "图表失败清单.csv",
                top=len(candidates),
            )
            if not report.offline_ready or report.chart_failure_count or report.chart_count != len(candidates):
                raise ValueError("离线报告或图表验收失败，请查看附件中的失败清单。")
            banner = (
                '<aside style="padding:18px;background:#fff3cd;color:#513c06;border-bottom:2px solid #d6a419">'
                f"<strong>云端小批量试运行：行情日期 {escape(asof)}</strong><br>"
                f"仅覆盖本轮指定的{len(requested)}只股票；成功评分{len(candidates)}只。"
                "保留原有全部等级，低等级不代表符合主升浪风格。"
                "非全市场筛选，未恢复旧电脑历史人工校对，不自动交易。</aside>"
            )
            html_path = output / "index.html"
            html_path.write_text(html_path.read_text(encoding="utf-8").replace("<body>", "<body>" + banner, 1), encoding="utf-8")
            summary.update(
                运行状态="完整接通" if len(selected) == len(requested) else "部分接通",
                评分输出数量=len(candidates), B级及以上数量=int(candidates["等级"].isin(["B", "A", "A+"]).sum()),
                图表数量=report.chart_count, 参与评分股票=selected,
                排除股票=[ticker for ticker in requested if ticker not in selected],
                评分摘要=candidates[["代码", "最新交易日", "综合评分", "等级"]].to_dict("records"),
                数据来源=sorted({source for ticker in list(基准代码) + selected for source in frames[ticker]["数据来源"].astype(str)}),
            )
        保存运行说明(output, summary)
        logger.info(json.dumps(summary, ensure_ascii=False))
        return summary
    except Exception as exc:
        summary.update(运行状态="失败", 失败原因=str(exc))
        保存运行说明(output, summary)
        raise


def main() -> int:
    """命令行默认拒绝下载，显式授权后才执行。"""
    parser = argparse.ArgumentParser(description="小批量公开日线到中文报告的云端试运行。")
    parser.add_argument("--allow-network", action="store_true", help="明确允许本轮获取公开日线。")
    parser.add_argument("--tickers", default=默认试运行代码, help="逗号分隔代码，最多30只，另加QQQ和SPY。")
    parser.add_argument("--output-dir", required=True, help="必须使用不存在或为空的报告目录。")
    args = parser.parse_args()
    try:
        运行云端试运行(tickers=args.tickers, output_dir=args.output_dir, allow_network=args.allow_network)
    except Exception as exc:
        get_logger("Mstock云端试运行").error(f"本轮未完成：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
