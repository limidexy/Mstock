"""每日网上热度选票流程。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from scripts.生成今日候选 import 格式化候选摘要行, 生成候选票报告  # noqa: E402
from scripts.生成网上热度池 import 运行生成网上热度池  # noqa: E402
from scripts.更新网上热度池行情 import 运行更新网上热度池行情  # noqa: E402
from src.data.web_hot_sources import 默认来源列表  # noqa: E402
from src.reports.csv_report import 保存候选票_csv, 保存失败清单, 生成候选票  # noqa: E402
from src.reports.html_report import 生成HTML报告  # noqa: E402
from src.reports.review_report import 默认待校对路径, 保存待校对_csv  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


默认热度池路径 = 项目根目录 / "data" / "processed" / "网上热度池.csv"
默认热度池报告路径 = 项目根目录 / "data" / "output" / "网上热度池生成报告.md"
默认热度来源失败路径 = 项目根目录 / "data" / "output" / "网上热度来源失败清单.csv"
默认热度下载失败路径 = 项目根目录 / "data" / "output" / "网上热度池下载失败清单.csv"
默认流程报告路径 = 项目根目录 / "data" / "output" / "每日网上热度流程报告.md"
默认股票池路径 = 项目根目录 / "data" / "processed" / "美股股票池.csv"
默认缓存目录 = 项目根目录 / "data" / "cache" / "daily"
默认候选输出路径 = 项目根目录 / "data" / "output" / "今日候选票.csv"
默认候选报告路径 = 项目根目录 / "data" / "output" / "候选票生成报告.md"
默认候选失败路径 = 项目根目录 / "data" / "output" / "候选票失败清单.csv"
默认HTML路径 = 项目根目录 / "data" / "output" / "今日候选票.html"
默认HTML报告路径 = 项目根目录 / "data" / "output" / "HTML报告验收报告.md"
默认HTML失败路径 = 项目根目录 / "data" / "output" / "HTML报告失败清单.csv"
默认图表目录 = 项目根目录 / "data" / "output" / "html_assets" / "charts"
默认来源 = ",".join(默认来源列表)


@dataclass(frozen=True)
class 每日网上热度流程结果:
    """每日网上热度流程结果。"""

    热度池数量: int
    网上来源数量: int
    来源成功数量: int
    来源失败数量: int
    涨幅榜数量: int
    成交量榜数量: int
    热门趋势数量: int
    异常放量数量: int
    阶段新高数量: int
    本轮尝试下载数量: int
    下载成功数量: int
    下载失败数量: int
    今日候选票数量: int
    等级分布: dict[str, int]
    top20: pd.DataFrame
    HTML报告路径: Path
    待校对文件路径: Path
    流程报告路径: Path


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="每日网上热度选票流程。")
    parser.add_argument("--limit", type=int, default=500, help="网上热度池最多处理数量。")
    parser.add_argument("--top", type=int, default=100, help="今日候选票输出前 N 名。")
    parser.add_argument("--skip-download", action="store_true", help="跳过热度池行情下载。")
    parser.add_argument("--skip-network", action="store_true", help="生成热度池时跳过联网来源。")
    parser.add_argument("--missing-only", action="store_true", help="只下载缺失行情缓存。")
    parser.add_argument("--provider", choices=["yfinance", "stooq", "auto"], default="auto", help="行情数据源。")
    parser.add_argument("--sleep-min", type=float, default=0.5, help="行情下载最小间隔秒数。")
    parser.add_argument("--sleep-max", type=float, default=1.5, help="行情下载最大间隔秒数。")
    parser.add_argument("--max-retries", type=int, default=2, help="最大重试次数。")
    parser.add_argument("--days", type=int, default=300, help="下载最近交易日数量。")
    parser.add_argument("--sources", type=str, default=默认来源, help="逗号分隔网上热度来源。")
    return parser.parse_args()


def 运行每日网上热度流程(args: argparse.Namespace) -> 每日网上热度流程结果:
    """执行每日网上热度选票流程。"""
    if args.limit <= 0:
        raise ValueError("参数错误：--limit 必须大于0。")
    if args.top <= 0:
        raise ValueError("参数错误：--top 必须大于0。")
    if args.sleep_min < 0 or args.sleep_max < args.sleep_min:
        raise ValueError("参数错误：请求间隔必须满足 0 <= sleep-min <= sleep-max。")

    hot_args = argparse.Namespace(
        limit=args.limit,
        sources=args.sources,
        timeout=15,
        sleep_min=1.0,
        sleep_max=3.0,
        max_retries=args.max_retries,
        use_cache=True,
        no_network=args.skip_network,
        output=str(默认热度池路径),
        report=str(默认热度池报告路径),
        failure_output=str(默认热度来源失败路径),
        cache_dir=str(默认缓存目录),
        stock_pool=str(默认股票池路径),
    )
    hot_result = 运行生成网上热度池(hot_args)

    download_attempted = 0
    download_success = 0
    download_failure = 0
    if not args.skip_download:
        download_args = argparse.Namespace(
            days=args.days,
            provider=args.provider,
            sleep_min=args.sleep_min,
            sleep_max=args.sleep_max,
            max_retries=args.max_retries,
            limit=args.limit,
            missing_only=args.missing_only,
            force=False,
            pool=str(默认热度池路径),
            failure_output=str(默认热度下载失败路径),
        )
        download_result = 运行更新网上热度池行情(download_args)
        download_attempted = download_result.本轮尝试下载数量
        download_success = download_result.下载成功数量
        download_failure = download_result.下载失败数量

    candidate_result = 生成候选票(
        cache_dir=默认缓存目录,
        stock_pool_path=默认股票池路径,
        top=args.top,
        min_score=0.0,
        min_grade="D",
        include_benchmark=False,
    )
    review_path = 默认待校对路径(项目根目录 / "data" / "review")
    保存候选票_csv(candidate_result.candidates, 默认候选输出路径)
    保存待校对_csv(candidate_result.candidates, review_path)
    保存失败清单(candidate_result.failures, 默认候选失败路径)
    默认候选报告路径.write_text(
        生成候选票报告(
            result=candidate_result,
            cache_dir=默认缓存目录,
            stock_pool_path=默认股票池路径,
            output_path=默认候选输出路径,
            review_path=review_path,
            report_path=默认候选报告路径,
            failure_path=默认候选失败路径,
        ),
        encoding="utf-8",
    )

    生成HTML报告(
        input_path=默认候选输出路径,
        cache_dir=默认缓存目录,
        output_path=默认HTML路径,
        charts_dir=默认图表目录,
        report_path=默认HTML报告路径,
        failure_path=默认HTML失败路径,
        top=args.top,
        min_score=0.0,
        min_grade="D",
        no_charts=False,
    )

    candidates = candidate_result.candidates
    grade_distribution = {str(k): int(v) for k, v in candidates["等级"].value_counts().to_dict().items()} if not candidates.empty else {}
    context = 每日网上热度流程结果(
        热度池数量=len(hot_result.数据),
        网上来源数量=len(hot_result.来源统计),
        来源成功数量=hot_result.来源成功数量,
        来源失败数量=hot_result.来源失败数量,
        涨幅榜数量=_count_flag(hot_result.数据, "是否涨幅榜"),
        成交量榜数量=_count_flag(hot_result.数据, "是否成交量榜"),
        热门趋势数量=_count_flag(hot_result.数据, "是否热门趋势"),
        异常放量数量=_count_category(hot_result.数据, "异常放量"),
        阶段新高数量=_count_flag(hot_result.数据, "是否阶段新高"),
        本轮尝试下载数量=download_attempted,
        下载成功数量=download_success,
        下载失败数量=download_failure,
        今日候选票数量=len(candidates),
        等级分布=grade_distribution,
        top20=candidates.head(20).copy(),
        HTML报告路径=默认HTML路径,
        待校对文件路径=review_path,
        流程报告路径=默认流程报告路径,
    )
    默认流程报告路径.parent.mkdir(parents=True, exist_ok=True)
    默认流程报告路径.write_text(生成每日网上热度流程报告(context), encoding="utf-8")
    return context


def 生成每日网上热度流程报告(context: 每日网上热度流程结果) -> str:
    """生成每日网上热度流程报告。"""
    lines = [
        "# 每日网上热度流程报告",
        "",
        f"1. 生成时间：{pd.Timestamp.now(tz='Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S')}",
        f"2. 热度池数量：{context.热度池数量}",
        f"3. 网上来源数量：{context.网上来源数量}",
        f"4. 来源成功数量：{context.来源成功数量}",
        f"5. 来源失败数量：{context.来源失败数量}",
        f"6. 涨幅榜数量：{context.涨幅榜数量}",
        f"7. 成交量榜数量：{context.成交量榜数量}",
        f"8. 热门趋势数量：{context.热门趋势数量}",
        f"9. 异常放量数量：{context.异常放量数量}",
        f"10. 阶段新高数量：{context.阶段新高数量}",
        f"11. 本轮尝试下载数量：{context.本轮尝试下载数量}",
        f"12. 下载成功数量：{context.下载成功数量}",
        f"13. 下载失败数量：{context.下载失败数量}",
        f"14. 今日候选票数量：{context.今日候选票数量}",
        "15. A+ / A / B / C / D 等级分布：",
    ]
    for grade in ["A+", "A", "B", "C", "D"]:
        lines.append(f"    - {grade}：{context.等级分布.get(grade, 0)}")
    lines.append("16. Top 20 摘要：")
    if context.top20.empty:
        lines.append("    - 无")
    else:
        for _, row in context.top20.iterrows():
            lines.append(f"    - {格式化候选摘要行(row)}")
    lines.extend(
        [
            f"17. HTML 报告路径：`{context.HTML报告路径}`",
            f"18. 待校对文件路径：`{context.待校对文件路径}`",
            "19. 是否建议人工校对：是",
            "",
            "## 重要说明",
            "",
            "- 热度来源不是买入理由。",
            "- 涨幅榜不是买入理由。",
            "- 成交量榜不是买入理由。",
            "- 它们只用于让系统优先覆盖市场活跃票。",
            "- 最终判断仍看主升浪评分和人工校对。",
            "- 本系统只做候选票筛选和复盘辅助，不自动交易，不给确定性买卖建议。",
        ]
    )
    return "\n".join(lines) + "\n"


def _count_flag(df: pd.DataFrame, column: str) -> int:
    if df.empty or column not in df.columns:
        return 0
    return int((df[column].astype(str) == "是").sum())


def _count_category(df: pd.DataFrame, keyword: str) -> int:
    if df.empty or "来源分类" not in df.columns:
        return 0
    return int(df["来源分类"].astype(str).str.contains(keyword, regex=False).sum())


def main() -> int:
    """命令行入口。"""
    args = parse_args()
    logger = get_logger("Mstock每日热度流程")
    try:
        context = 运行每日网上热度流程(args)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"每日网上热度流程失败：{exc}")
        return 1

    logger.info(f"网上热度池数量：{context.热度池数量}")
    logger.info(f"本轮下载成功：{context.下载成功数量}，失败：{context.下载失败数量}")
    logger.info(f"今日候选票数量：{context.今日候选票数量}")
    logger.info(f"HTML 报告路径：{context.HTML报告路径}")
    logger.info(f"每日网上热度流程报告已生成：{context.流程报告路径}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
