"""生成今日中文候选票和待校对文件。

默认从本地日线缓存重新计算特征和评分，不联网、不下载行情、不自动交易。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import sys
from pathlib import Path

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from src.reports.csv_report import 候选票核心字段, 从评分样例生成候选, 保存候选票_csv, 保存失败清单, 生成候选票  # noqa: E402
from src.reports.review_report import 默认待校对路径, 保存待校对_csv  # noqa: E402
from src.utils.chinese import get_display_label  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


默认缓存目录 = 项目根目录 / "data" / "cache" / "daily"
默认股票池路径 = 项目根目录 / "data" / "processed" / "美股股票池.csv"
默认输出路径 = 项目根目录 / "data" / "output" / "今日候选票.csv"
默认报告路径 = 项目根目录 / "data" / "output" / "候选票生成报告.md"
默认失败路径 = 项目根目录 / "data" / "output" / "候选票失败清单.csv"


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="生成今日中文候选票。")
    parser.add_argument("--cache-dir", type=str, default=str(默认缓存目录), help="日线缓存目录。")
    parser.add_argument("--stock-pool", type=str, default=str(默认股票池路径), help="股票池元数据路径。")
    parser.add_argument("--output", type=str, default=str(默认输出路径), help="今日候选票输出路径。")
    parser.add_argument("--review-output", type=str, default=None, help="待校对 CSV 输出路径。")
    parser.add_argument("--report", type=str, default=str(默认报告路径), help="候选票生成报告路径。")
    parser.add_argument("--top", type=int, default=100, help="输出综合评分前 N 名，0 表示不限制。")
    parser.add_argument("--min-score", type=float, default=0.0, help="最低综合评分。")
    parser.add_argument("--min-grade", choices=["D", "C", "B", "A", "A+"], default="D", help="最低等级。")
    parser.add_argument("--include-benchmark", action="store_true", help="允许 QQQ、SPY 出现在候选票输出中。")
    parser.add_argument("--from-score-sample", type=str, default=None, help="调试用：直接从评分样例生成候选票。")
    return parser.parse_args()


def main() -> int:
    """生成今日候选票。"""
    args = parse_args()
    logger = get_logger("Mstock今日候选")
    if args.top < 0:
        logger.error("参数错误：--top 不能小于0。")
        return 1
    if args.min_score < 0 or args.min_score > 100:
        logger.error("参数错误：--min-score 必须在0到100之间。")
        return 1

    cache_dir = Path(args.cache_dir)
    stock_pool_path = Path(args.stock_pool)
    output_path = Path(args.output)
    review_path = Path(args.review_output) if args.review_output else 默认待校对路径(项目根目录 / "data" / "review")
    report_path = Path(args.report)

    try:
        if args.from_score_sample:
            result = 从评分样例生成候选(
                score_sample_path=args.from_score_sample,
                stock_pool_path=stock_pool_path,
                top=args.top,
                min_score=args.min_score,
                min_grade=args.min_grade,
                include_benchmark=args.include_benchmark,
            )
        else:
            result = 生成候选票(
                cache_dir=cache_dir,
                stock_pool_path=stock_pool_path,
                top=args.top,
                min_score=args.min_score,
                min_grade=args.min_grade,
                include_benchmark=args.include_benchmark,
            )
        保存候选票_csv(result.candidates, output_path)
        保存待校对_csv(result.candidates, review_path)
        保存失败清单(result.failures, 默认失败路径)
        report = 生成候选票报告(
            result=result,
            cache_dir=cache_dir,
            stock_pool_path=stock_pool_path,
            output_path=output_path,
            review_path=review_path,
            report_path=report_path,
            failure_path=默认失败路径,
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    except Exception as exc:
        logger.error(f"生成今日候选失败：{exc}")
        return 1

    logger.info(f"今日候选票已生成：{output_path}")
    logger.info(f"待校对文件已生成：{review_path}")
    logger.info(f"候选票生成报告已生成：{report_path}")
    logger.info(f"候选数量：{len(result.candidates)}，失败数量：{len(result.failures)}")
    return 0


def 生成候选票报告(
    result,
    cache_dir: Path,
    stock_pool_path: Path,
    output_path: Path,
    review_path: Path,
    report_path: Path,
    failure_path: Path,
) -> str:
    """生成候选票中文报告。"""
    candidates = result.candidates
    severe_issues: list[str] = []
    missing_fields = [field for field in 候选票核心字段 if field not in candidates.columns]
    if not result.qqq_exists and not result.used_score_sample:
        severe_issues.append("QQQ 基准缓存缺失")
    if not result.spy_exists and not result.used_score_sample:
        severe_issues.append("SPY 基准缓存缺失")
    if len(candidates) == 0:
        severe_issues.append("成功候选数量为0")
    if missing_fields:
        severe_issues.append(f"核心输出字段缺失：{'、'.join(missing_fields)}")
    if not candidates.empty and not candidates["综合评分"].between(0, 100).all():
        severe_issues.append("综合评分越界")
    if not candidates.empty and not candidates["综合评分"].is_monotonic_decreasing:
        severe_issues.append("排名不是按综合评分降序")

    recommend = not severe_issues
    grade_distribution = candidates["等级"].value_counts().to_dict() if not candidates.empty else {}
    lines = [
        "# 候选票生成报告",
        "",
        f"1. 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"2. 缓存目录：`{cache_dir}`",
        f"3. 股票池元数据路径：`{stock_pool_path}`",
        f"4. 缓存文件数量：{result.cache_file_count}",
        f"5. 基准 QQQ 是否存在：{'是' if result.qqq_exists or result.used_score_sample else '否'}",
        f"6. 基准 SPY 是否存在：{'是' if result.spy_exists or result.used_score_sample else '否'}",
        f"7. 尝试处理标的数量：{result.attempted_count}",
        f"8. 成功生成候选数量：{len(candidates)}",
        f"9. 失败数量：{len(result.failures)}",
        f"10. 是否默认排除 QQQ/SPY：{'否' if result.include_benchmark else '是'}",
        f"11. 是否使用评分样例模式：{'是' if result.used_score_sample else '否'}",
        f"12. 输出文件路径：`{output_path}`",
        f"13. 待校对文件路径：`{review_path}`",
        f"14. 失败清单路径：`{failure_path}`",
        "15. 等级分布：",
    ]
    if grade_distribution:
        for grade, count in grade_distribution.items():
            lines.append(f"    - {grade}：{count}")
    else:
        lines.append("    - 无")
    lines.append("16. Top 10 摘要：")
    if candidates.empty:
        lines.append("    - 无")
    else:
        for _, row in candidates.head(10).iterrows():
            lines.append(f"    - {格式化候选摘要行(row)}")
    lines.extend(
        [
            "17. 当前结果是否只基于已缓存标的：是，当前结果只基于已缓存标的，不代表全市场。",
            "18. 是否建议进入第 10 步“中文 HTML 报告”：",
            f"    - {'可以进入第 10 步中文 HTML 报告' if recommend else '不建议进入第 10 步中文 HTML 报告'}",
            "",
            "## 补充提示",
            "",
            f"- 股票池元数据提示：{result.metadata_warning or '无'}",
            "- 本系统只做候选票筛选和复盘辅助，不自动交易，不给确定性买卖建议。",
            "",
            "## 严重问题",
            "",
        ]
    )
    if severe_issues:
        for issue in severe_issues:
            lines.append(f"- {issue}")
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def 格式化候选摘要行(row: pd.Series) -> str:
    """格式化报告里的候选摘要，显示中文名和短线涨幅。"""
    label = get_display_label(
        row.get("代码", ""),
        row.get("中文名称", ""),
        row.get("名称", ""),
        row.get("是否ETF", ""),
    )
    return (
        f"第{int(row['排名'])}名 {label}："
        f"综合评分{_格式化分数(row.get('综合评分'))}，等级{row.get('等级', '')}，"
        f"当日涨幅{_格式化百分比(row.get('当日涨幅'))}，5日涨幅{_格式化百分比(row.get('5日涨幅'))}，"
        f"理由：{row.get('入选理由', '')}"
    )


def _格式化百分比(value) -> str:
    """格式化涨幅。"""
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "不足数据"
    return f"{float(number) * 100:.2f}%"


def _格式化分数(value) -> str:
    """格式化评分。"""
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "不足数据"
    return f"{float(number):.1f}"


if __name__ == "__main__":
    raise SystemExit(main())
