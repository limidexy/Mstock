"""单票漏选诊断脚本。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from scripts.生成技术特征样例 import 计算单票特征  # noqa: E402
from src.reports.csv_report import 生成候选票  # noqa: E402
from src.scoring.scoring_pipeline import score_feature_dataframe_with_failures  # noqa: E402
from src.utils.chinese import get_chinese_display_name  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


默认股票池路径 = 项目根目录 / "data" / "processed" / "美股股票池.csv"
默认下载候选池路径列表 = [
    项目根目录 / "data" / "processed" / "下载候选池_200.csv",
    项目根目录 / "data" / "processed" / "下载候选池_500.csv",
]
默认日线缓存目录 = 项目根目录 / "data" / "cache" / "daily"
默认候选票路径 = 项目根目录 / "data" / "output" / "今日候选票.csv"
默认失败清单路径列表 = [
    项目根目录 / "data" / "output" / "下载失败清单.csv",
    项目根目录 / "data" / "output" / "技术特征失败清单.csv",
    项目根目录 / "data" / "output" / "评分失败清单.csv",
    项目根目录 / "data" / "output" / "候选票失败清单.csv",
    项目根目录 / "data" / "output" / "HTML报告失败清单.csv",
]

诊断字段 = [
    "代码",
    "日期",
    "收盘价",
    "当日涨幅",
    "3日涨幅",
    "5日涨幅",
    "10日涨幅",
    "20日涨幅",
    "60日涨幅",
    "成交量",
    "成交额",
    "20日量比",
    "MA5",
    "MA10",
    "MA20",
    "MA30",
    "MA60",
    "MA120",
    "MA250",
    "MA5乖离",
    "MA10乖离",
    "MA20乖离",
    "是否均线多头排列",
    "是否短期均线向上发散",
    "MACD状态",
    "突破状态",
    "相对强度状态",
    "是否突破20日新高",
    "是否突破60日新高",
    "是否突破120日新高",
    "距离20日新高",
    "距离60日新高",
    "距离120日新高",
    "当日收盘位置",
    "风险标签",
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
    "评分解释",
    "观察价",
    "失效位",
]


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="诊断单只股票为什么没有进入候选票。")
    parser.add_argument("--ticker", required=True, help="需要诊断的代码，例如 NBIS。")
    parser.add_argument("--download-if-missing", action="store_true", help="缺少缓存时只下载该代码。")
    parser.add_argument("--output", default=None, help="诊断 CSV 输出路径。")
    parser.add_argument("--report", default=None, help="诊断报告输出路径。")
    return parser.parse_args()


def main() -> int:
    """运行单票诊断。"""
    args = parse_args()
    logger = get_logger("Mstock单票诊断")
    ticker = args.ticker.strip().upper()
    output_path = Path(args.output) if args.output else 项目根目录 / "data" / "output" / f"{ticker}_单票诊断.csv"
    report_path = Path(args.report) if args.report else 项目根目录 / "data" / "output" / f"{ticker}_单票诊断报告.md"

    try:
        result = 诊断单票(ticker=ticker, output_path=output_path, report_path=report_path, download_if_missing=args.download_if_missing)
    except Exception as exc:
        logger.error(f"{ticker} 单票诊断失败：{exc}")
        return 1

    logger.info(f"{ticker} 单票诊断 CSV 已生成：{result['诊断CSV路径']}")
    logger.info(f"{ticker} 单票诊断报告已生成：{result['诊断报告路径']}")
    return 0


def 诊断单票(ticker: str, output_path: Path, report_path: Path, download_if_missing: bool = False) -> dict:
    """执行单票诊断并写入 CSV 和报告。"""
    ticker = ticker.strip().upper()
    stock_pool_info = 查询股票池(ticker)
    candidate_pool_info = 查询下载候选池(ticker)
    failure_info = 查询失败清单(ticker)
    cache_path = 默认日线缓存目录 / f"{ticker}.csv"

    if not cache_path.exists() and download_if_missing:
        只下载单票(ticker)

    cache_info = 检查缓存(ticker)
    diagnostic_df = pd.DataFrame(columns=诊断字段)
    score_info: dict = {}
    ranking_info: dict = {"当前候选票存在": False, "全缓存排名": None, "top100会被过滤": None}

    if cache_info["缓存存在"] and not cache_info["是否空"]:
        diagnostic_df, score_info = 计算单票诊断(ticker)
        ranking_info = 计算排名信息(ticker)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostic_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    report_text = 生成诊断报告(
        ticker=ticker,
        stock_pool_info=stock_pool_info,
        candidate_pool_info=candidate_pool_info,
        cache_info=cache_info,
        failure_info=failure_info,
        score_info=score_info,
        ranking_info=ranking_info,
        output_path=output_path,
        report_path=report_path,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    return {"诊断CSV路径": output_path, "诊断报告路径": report_path}


def 查询股票池(ticker: str) -> dict:
    """查询代码是否在美股股票池。"""
    if not 默认股票池路径.exists():
        return {"存在": False, "原因": "美股股票池文件不存在。", "记录": {}}
    df = pd.read_csv(默认股票池路径, encoding="utf-8-sig")
    rows = df[df["代码"].astype(str).str.upper() == ticker]
    if rows.empty:
        return {"存在": False, "原因": "美股股票池没有该代码。", "记录": {}}
    return {"存在": True, "原因": "已匹配美股股票池。", "记录": rows.iloc[0].to_dict()}


def 查询下载候选池(ticker: str) -> dict:
    """查询代码是否在下载候选池。"""
    matches = []
    existing_files = []
    for path in 默认下载候选池路径列表:
        if not path.exists():
            continue
        existing_files.append(str(path))
        df = pd.read_csv(path, encoding="utf-8-sig")
        rows = df[df["代码"].astype(str).str.upper() == ticker]
        if not rows.empty:
            matches.append({"路径": str(path), "记录": rows.iloc[0].to_dict()})
    if matches:
        return {"存在": True, "原因": "已进入下载候选池。", "匹配": matches, "已检查文件": existing_files}
    return {
        "存在": False,
        "原因": "不在验证种子列表中；当前200候选池的分层抽样按代码首字母轮询补足，每组只取前几只，NBIS在N组排序位置靠后，因此未被抽到。",
        "匹配": [],
        "已检查文件": existing_files,
    }


def 查询失败清单(ticker: str) -> dict:
    """查询代码是否出现在各类失败清单。"""
    records = []
    for path in 默认失败清单路径列表:
        if not path.exists():
            continue
        df = pd.read_csv(path, encoding="utf-8-sig")
        if "代码" not in df.columns:
            continue
        rows = df[df["代码"].astype(str).str.upper() == ticker]
        for _, row in rows.iterrows():
            data = row.to_dict()
            data["失败清单路径"] = str(path)
            records.append(data)
    return {"存在": bool(records), "记录": records}


def 检查缓存(ticker: str) -> dict:
    """检查单票缓存。"""
    path = 默认日线缓存目录 / f"{ticker}.csv"
    required = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "数据来源"]
    if not path.exists():
        return {"缓存存在": False, "是否空": True, "行数": 0, "最新交易日": "", "最新收盘价": "", "必要字段完整": False, "缺失字段": required}
    df = pd.read_csv(path, encoding="utf-8-sig")
    missing = [column for column in required if column not in df.columns]
    latest = df.sort_values("日期").tail(1).iloc[0].to_dict() if not df.empty else {}
    return {
        "缓存存在": True,
        "是否空": df.empty,
        "行数": len(df),
        "最新交易日": latest.get("日期", ""),
        "最新收盘价": latest.get("收盘价", ""),
        "必要字段完整": not missing,
        "缺失字段": missing,
    }


def 只下载单票(ticker: str) -> None:
    """调用现有行情脚本下载单票。"""
    command = [
        sys.executable,
        str(项目根目录 / "scripts" / "更新行情数据.py"),
        "--provider",
        "auto",
        "--tickers",
        ticker,
        "--days",
        "300",
        "--force",
        "--sleep-min",
        "0.5",
        "--sleep-max",
        "1.5",
        "--max-retries",
        "2",
    ]
    subprocess.run(command, cwd=项目根目录, check=True)


def 计算单票诊断(ticker: str) -> tuple[pd.DataFrame, dict]:
    """计算单票最新技术特征和评分。"""
    daily = pd.read_csv(默认日线缓存目录 / f"{ticker}.csv", encoding="utf-8-sig")
    qqq = pd.read_csv(默认日线缓存目录 / "QQQ.csv", encoding="utf-8-sig")
    spy = pd.read_csv(默认日线缓存目录 / "SPY.csv", encoding="utf-8-sig")
    features = 计算单票特征(daily, qqq, spy)
    latest = features.tail(1).reset_index(drop=True)
    scoring = score_feature_dataframe_with_failures(latest)
    if scoring.scored.empty:
        raise ValueError(f"{ticker} 评分失败：{scoring.failures.to_dict(orient='records')}")
    combined = latest.iloc[0].to_dict()
    combined.update(scoring.scored.iloc[0].to_dict())
    for field in 诊断字段:
        combined.setdefault(field, "")
    diagnostic_df = pd.DataFrame([combined])[诊断字段]
    return diagnostic_df, combined


def 计算排名信息(ticker: str) -> dict:
    """计算该票在当前全部缓存评分中的排名。"""
    current_exists = False
    if 默认候选票路径.exists():
        current = pd.read_csv(默认候选票路径, encoding="utf-8-sig")
        current_exists = ticker in set(current.get("代码", pd.Series(dtype=str)).astype(str).str.upper())
    all_result = 生成候选票(
        cache_dir=默认日线缓存目录,
        stock_pool_path=默认股票池路径,
        top=0,
        min_score=0,
        min_grade="D",
        include_benchmark=False,
    )
    candidates = all_result.candidates
    row = candidates[candidates["代码"].astype(str).str.upper() == ticker]
    if row.empty:
        return {"当前候选票存在": current_exists, "全缓存排名": None, "top100会被过滤": None, "候选总数": len(candidates)}
    rank = int(row.iloc[0]["排名"])
    return {
        "当前候选票存在": current_exists,
        "全缓存排名": rank,
        "top100会被过滤": rank > 100,
        "候选总数": len(candidates),
        "全缓存评分": row.iloc[0].to_dict(),
    }


def 生成诊断报告(
    ticker: str,
    stock_pool_info: dict,
    candidate_pool_info: dict,
    cache_info: dict,
    failure_info: dict,
    score_info: dict,
    ranking_info: dict,
    output_path: Path,
    report_path: Path,
) -> str:
    """生成单票中文诊断报告。"""
    main_reason = 判断漏选原因(stock_pool_info, candidate_pool_info, cache_info, failure_info, score_info, ranking_info)
    suggest_rule = "否。本次不建议因为单票漏选直接修改评分规则；应先通过用户关注票机制保证诊断覆盖。"
    suggest_pool = "是。NBIS 在股票池中但未进入下载候选池，建议允许用户关注票强制加入下载候选池。"
    suggest_watchlist = "是。建议新增 data/manual/用户关注票.csv，但关注票不能自动加分，也不能绕过评分系统。"

    lines = [
        f"# {ticker} 单票漏选诊断报告",
        "",
        f"1. 诊断时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"2. {ticker} 是否在股票池：{'是' if stock_pool_info['存在'] else '否'}",
        f"3. {ticker} 是否在下载候选池：{'是' if candidate_pool_info['存在'] else '否'}",
        f"4. {ticker} 是否有行情缓存：{'是' if cache_info['缓存存在'] else '否'}",
        f"5. {ticker} 是否出现在失败清单：{'是' if failure_info['存在'] else '否'}",
        f"6. {ticker} 最新交易日：{cache_info.get('最新交易日', '') or '不足数据'}",
        f"7. {ticker} 最新收盘价：{_fmt_number(score_info.get('收盘价', cache_info.get('最新收盘价', '')))}",
        f"8. {ticker} 当日涨幅：{_fmt_percent(score_info.get('当日涨幅'))}",
        f"9. {ticker} 5日涨幅：{_fmt_percent(score_info.get('5日涨幅'))}",
        f"10. {ticker} 20日涨幅：{_fmt_percent(score_info.get('20日涨幅'))}",
        f"11. {ticker} 60日涨幅：{_fmt_percent(score_info.get('60日涨幅'))}",
        f"12. {ticker} 趋势结构分：{_fmt_score(score_info.get('趋势结构分'))}",
        f"13. {ticker} 突破强度分：{_fmt_score(score_info.get('突破强度分'))}",
        f"14. {ticker} 量能强度分：{_fmt_score(score_info.get('量能强度分'))}",
        f"15. {ticker} 相对强度分：{_fmt_score(score_info.get('相对强度分'))}",
        f"16. {ticker} 主升浪形态分：{_fmt_score(score_info.get('主升浪形态分'))}",
        f"17. {ticker} 风险扣分：{_fmt_score(score_info.get('风险扣分'))}",
        f"18. {ticker} 综合评分：{_fmt_score(score_info.get('综合评分'))}",
        f"19. {ticker} 等级：{score_info.get('等级', '不足数据')}",
        f"20. {ticker} 入选理由：{score_info.get('入选理由', '不足数据')}",
        f"21. {ticker} 风险标签：{score_info.get('风险标签', '不足数据')}",
        f"22. {ticker} 没进入候选票的主要原因：{main_reason}",
        f"23. 是否建议修改下载候选池规则：{suggest_pool}",
        f"24. 是否建议修改评分规则：{suggest_rule}",
        f"25. 是否建议加入“用户关注票列表”：{suggest_watchlist}",
        "",
        "## 股票池检查",
        "",
        f"- 美股股票池记录：{stock_pool_info.get('记录', {}) or '无'}",
        f"- 下载候选池检查文件：{'、'.join(candidate_pool_info.get('已检查文件', [])) or '无'}",
        f"- 下载候选池未命中说明：{candidate_pool_info.get('原因', '')}",
        "",
        "## 缓存检查",
        "",
        f"- 缓存行数：{cache_info.get('行数', 0)}",
        f"- 必要字段完整：{'是' if cache_info.get('必要字段完整') else '否'}",
        f"- 缺失字段：{'、'.join(cache_info.get('缺失字段', [])) if cache_info.get('缺失字段') else '无'}",
        "",
        "## 失败清单检查",
        "",
    ]
    if failure_info["存在"]:
        for record in failure_info["记录"]:
            lines.append(f"- {record}")
    else:
        lines.append("- 未发现 NBIS 出现在任何失败清单。")

    lines.extend(
        [
            "",
            "## 当前候选票与排名",
            "",
            f"- NBIS 是否已经在当前今日候选票里：{'是' if ranking_info.get('当前候选票存在') else '否'}",
            f"- NBIS 如果参与当前全部缓存评分，排名：{ranking_info.get('全缓存排名') or '不足数据'} / {ranking_info.get('候选总数') or '不足数据'}",
            f"- 是否因为 top 100 被挤掉：{'是' if ranking_info.get('top100会被过滤') else '否'}",
            "- 是否因为 --min-score 被过滤：否，当前诊断按 min-score 0 计算。",
            "- 是否因为 --min-grade 被过滤：否，当前诊断按最低 D 级计算。",
            f"- 是否因为下载候选池漏掉：{'是' if not candidate_pool_info['存在'] else '否'}",
            f"- 是否因为没有行情缓存：{'否，当前已补齐缓存' if cache_info['缓存存在'] else '是'}",
            f"- 是否因为计算失败：{'是' if not score_info else '否'}",
            f"- 是否因为风险扣分过高：{'是' if _to_float(score_info.get('风险扣分')) >= 10 else '否'}",
            f"- 是否因为突破分、趋势分或相对强度分不足：{判断分项不足(score_info)}",
            "",
            "## 用户关注票机制建议",
            "",
            "建议新增 `data/manual/用户关注票.csv`，字段如下：",
            "",
            "```text",
            "代码",
            "备注",
            "加入日期",
            "是否强制下载",
            "是否强制诊断",
            "```",
            "",
            "建议逻辑：用户关注票可以强制加入下载候选池、强制生成单票诊断；但不能自动加分，不能绕过评分系统直接进入高等级。如果评分低，也必须如实显示分数和原因。",
            "",
            f"## 输出文件",
            "",
            f"- 诊断 CSV：`{output_path}`",
            f"- 诊断报告：`{report_path}`",
        ]
    )
    return "\n".join(lines) + "\n"


def 判断漏选原因(stock_pool_info: dict, candidate_pool_info: dict, cache_info: dict, failure_info: dict, score_info: dict, ranking_info: dict) -> str:
    """判断漏选主因。"""
    if not stock_pool_info["存在"]:
        return "NBIS 不在美股股票池；若是用户明确关注票，建议允许用户关注票绕过股票池进入单票下载和诊断。"
    if not candidate_pool_info["存在"] and cache_info["缓存存在"]:
        rank_text = f"；当前补齐缓存后参与全缓存排序为第{ranking_info.get('全缓存排名')}名" if ranking_info.get("全缓存排名") else ""
        return f"原始漏选主因是 NBIS 没进入下载候选池，导致今日候选票生成时没有行情缓存、没有参与评分{rank_text}。"
    if not candidate_pool_info["存在"] and not cache_info["缓存存在"]:
        return "NBIS 在美股股票池，但不在下载候选池，因此此前没有行情缓存，也就无法进入候选票评分。"
    if failure_info["存在"]:
        return "NBIS 出现在失败清单，需要先修复失败原因。"
    if not cache_info["缓存存在"]:
        return "NBIS 没有行情缓存，无法计算特征和评分。"
    if ranking_info.get("top100会被过滤"):
        return f"NBIS 已可评分，但在当前全部缓存标的中排名第{ranking_info.get('全缓存排名')}，超过 top 100 输出范围。"
    if not ranking_info.get("当前候选票存在"):
        return "NBIS 当前已可评分，但今日候选票是在下载 NBIS 之前生成的；需要重新生成候选票才会按真实排名参与输出。"
    return "NBIS 已在当前候选票中。"


def 判断分项不足(score_info: dict) -> str:
    """判断关键分项是否不足。"""
    if not score_info:
        return "不足数据"
    weak = []
    if _to_float(score_info.get("趋势结构分")) < 15:
        weak.append("趋势结构分不足")
    if _to_float(score_info.get("突破强度分")) < 15:
        weak.append("突破强度分不足")
    if _to_float(score_info.get("相对强度分")) < 8:
        weak.append("相对强度分不足")
    return "是，" + "、".join(weak) if weak else "否，主要分项没有明显短板"


def _to_float(value) -> float:
    number = pd.to_numeric(value, errors="coerce")
    return float(number) if not pd.isna(number) else 0.0


def _fmt_percent(value) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "不足数据"
    return f"{float(number) * 100:.2f}%"


def _fmt_score(value) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "不足数据"
    return f"{float(number):.1f}"


def _fmt_number(value) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "不足数据"
    return f"{float(number):.4f}".rstrip("0").rstrip(".")


if __name__ == "__main__":
    raise SystemExit(main())
