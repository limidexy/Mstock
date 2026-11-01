"""扩大真实行情数据范围并验证完整候选链路。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import sys
from pathlib import Path

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from scripts.更新行情数据 import 创建数据源  # noqa: E402
from scripts.生成今日候选 import 格式化候选摘要行, 生成候选票报告  # noqa: E402
from src.data.cache import 批量更新日线缓存, 日线缓存路径, 是否临时限流错误, 统计缓存文件数量  # noqa: E402
from src.data.universe_selection import 最大自动候选池规模, 构建下载候选池, 生成候选池构建报告  # noqa: E402
from src.reports.csv_report import 保存候选票_csv, 保存失败清单, 生成候选票  # noqa: E402
from src.reports.html_report import 生成HTML报告  # noqa: E402
from src.reports.review_report import 默认待校对路径, 保存待校对_csv  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


默认股票池路径 = 项目根目录 / "data" / "processed" / "美股股票池.csv"
默认缓存根目录 = 项目根目录 / "data" / "cache"
默认日线缓存目录 = 默认缓存根目录 / "daily"
默认候选输出路径 = 项目根目录 / "data" / "output" / "今日候选票.csv"
默认候选报告路径 = 项目根目录 / "data" / "output" / "候选票生成报告.md"
默认候选失败路径 = 项目根目录 / "data" / "output" / "候选票失败清单.csv"
默认下载失败路径 = 项目根目录 / "data" / "output" / "下载失败清单.csv"
默认HTML路径 = 项目根目录 / "data" / "output" / "今日候选票.html"
默认HTML报告路径 = 项目根目录 / "data" / "output" / "HTML报告验收报告.md"
默认HTML失败路径 = 项目根目录 / "data" / "output" / "HTML报告失败清单.csv"
默认图表目录 = 项目根目录 / "data" / "output" / "html_assets" / "charts"
默认验证报告路径 = 项目根目录 / "data" / "output" / "真实候选池验证报告.md"
默认候选池构建报告路径 = 项目根目录 / "data" / "output" / "下载候选池构建报告.md"


@dataclass
class 真实验证上下文:
    """真实候选池验证上下文。"""

    目标候选池规模: int
    候选池路径: Path
    候选池数量: int
    下载前缓存数量: int
    下载后缓存数量: int
    尝试下载数量: int
    成功下载数量: int
    失败下载数量: int
    provider: str
    是否遇到限流: bool
    候选票路径: Path
    待校对路径: Path
    HTML路径: Path
    失败清单路径: Path
    今日候选票数量: int
    等级分布: dict[str, int]
    top20: pd.DataFrame
    qqq存在: bool
    spy存在: bool
    html已生成: bool
    dry_run: bool
    skip_download: bool
    skip_html: bool
    严重问题: list[str]


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="扩大真实数据下载并验证候选池。")
    parser.add_argument("--target-size", type=int, default=200, help="目标下载候选池规模，默认200，最大500。")
    parser.add_argument("--days", type=int, default=300, help="下载最近交易日数量。")
    parser.add_argument("--provider", choices=["yfinance", "stooq", "auto"], default="auto", help="行情数据源。")
    parser.add_argument("--sleep-min", type=float, default=0.5, help="请求最小间隔秒数。")
    parser.add_argument("--sleep-max", type=float, default=1.5, help="请求最大间隔秒数。")
    parser.add_argument("--max-retries", type=int, default=2, help="单只标的最大重试次数。")
    parser.add_argument("--top", type=int, default=100, help="候选票输出前 N 名。")
    parser.add_argument("--min-score", type=float, default=0.0, help="候选票最低评分。")
    parser.add_argument("--skip-download", action="store_true", help="跳过下载，基于已有缓存继续生成候选和HTML。")
    parser.add_argument("--skip-html", action="store_true", help="跳过 HTML 报告生成。")
    parser.add_argument("--dry-run", action="store_true", help="只构建候选池和下载计划，不下载。")
    return parser.parse_args()


def 获取待下载代码(codes: list[str], cache_root: Path) -> list[str]:
    """只选择还没有日线缓存的代码，减少重复请求。"""
    pending = []
    for code in codes:
        if not 日线缓存路径(cache_root, code).exists():
            pending.append(code)
    return pending


def 运行真实数据验证(args: argparse.Namespace) -> 真实验证上下文:
    """执行真实候选池验证主流程。"""
    if args.target_size <= 0:
        raise ValueError("参数错误：--target-size 必须大于0。")
    if args.target_size > 最大自动候选池规模:
        raise ValueError("目标规模超过500，本轮不会自动下载；请先完成200规模验证后再扩大。")
    if args.days <= 0:
        raise ValueError("参数错误：--days 必须大于0。")
    if args.sleep_min < 0 or args.sleep_max < args.sleep_min:
        raise ValueError("参数错误：请求间隔必须满足 0 <= sleep-min <= sleep-max。")

    candidate_pool_path = 项目根目录 / "data" / "processed" / f"下载候选池_{args.target_size}.csv"
    build_result = 构建下载候选池(默认股票池路径, target_size=args.target_size, output_path=candidate_pool_path)
    默认候选池构建报告路径.parent.mkdir(parents=True, exist_ok=True)
    默认候选池构建报告路径.write_text(生成候选池构建报告(build_result), encoding="utf-8")

    codes = build_result.数据["代码"].astype(str).str.upper().tolist()
    cache_before = 统计缓存文件数量(默认缓存根目录)
    pending = 获取待下载代码(codes, 默认缓存根目录)
    success_count = 0
    failure_count = 0
    limit_hit = False
    failure_path = 默认下载失败路径

    if args.dry_run or args.skip_download:
        cache_after = cache_before
    else:
        provider = 创建数据源(args.provider)
        download_result = 批量更新日线缓存(
            provider=provider,
            tickers=pending,
            cache_dir=默认缓存根目录,
            days=args.days,
            force=False,
            failure_path=默认下载失败路径,
            max_retries=args.max_retries,
            sleep_min=args.sleep_min,
            sleep_max=args.sleep_max,
        )
        success_count = download_result.成功数量
        failure_count = download_result.失败数量
        failure_path = download_result.失败清单路径
        limit_hit = any(是否临时限流错误(str(item.get("失败原因", ""))) for item in download_result.失败清单)
        cache_after = 统计缓存文件数量(默认缓存根目录)

    candidate_count = 0
    grade_distribution: dict[str, int] = {}
    top20 = pd.DataFrame()
    review_path = 默认待校对路径(项目根目录 / "data" / "review")
    html_generated = 默认HTML路径.exists()

    if not args.dry_run:
        candidate_result = 生成候选票(
            cache_dir=默认日线缓存目录,
            stock_pool_path=默认股票池路径,
            top=args.top,
            min_score=args.min_score,
            min_grade="D",
            include_benchmark=False,
        )
        保存候选票_csv(candidate_result.candidates, 默认候选输出路径)
        保存待校对_csv(candidate_result.candidates, review_path)
        保存失败清单(candidate_result.failures, 默认候选失败路径)
        candidate_report = 生成候选票报告(
            result=candidate_result,
            cache_dir=默认日线缓存目录,
            stock_pool_path=默认股票池路径,
            output_path=默认候选输出路径,
            review_path=review_path,
            report_path=默认候选报告路径,
            failure_path=默认候选失败路径,
        )
        默认候选报告路径.write_text(candidate_report, encoding="utf-8")
        candidate_count = len(candidate_result.candidates)
        if not candidate_result.candidates.empty:
            grade_distribution = {str(k): int(v) for k, v in candidate_result.candidates["等级"].value_counts().to_dict().items()}
            top20 = candidate_result.candidates.head(20).copy()

        if not args.skip_html:
            html_result = 生成HTML报告(
                input_path=默认候选输出路径,
                cache_dir=默认日线缓存目录,
                output_path=默认HTML路径,
                charts_dir=默认图表目录,
                report_path=默认HTML报告路径,
                failure_path=默认HTML失败路径,
                top=args.top,
                min_score=args.min_score,
                min_grade="D",
                no_charts=False,
            )
            html_generated = html_result.html_path.exists()
        else:
            html_generated = 默认HTML路径.exists()

    qqq_exists = 日线缓存路径(默认缓存根目录, "QQQ").exists()
    spy_exists = 日线缓存路径(默认缓存根目录, "SPY").exists()
    severe_issues = 生成严重问题(
        qqq_exists=qqq_exists,
        spy_exists=spy_exists,
        cache_before=cache_before,
        cache_after=cache_after,
        attempted=len(pending) if not (args.dry_run or args.skip_download) else 0,
        success=success_count,
        failure=failure_count,
        candidate_count=candidate_count,
        html_generated=html_generated,
        dry_run=args.dry_run,
        skip_html=args.skip_html,
    )
    context = 真实验证上下文(
        目标候选池规模=args.target_size,
        候选池路径=candidate_pool_path,
        候选池数量=len(build_result.数据),
        下载前缓存数量=cache_before,
        下载后缓存数量=cache_after,
        尝试下载数量=len(pending) if not (args.dry_run or args.skip_download) else 0,
        成功下载数量=success_count,
        失败下载数量=failure_count,
        provider=args.provider,
        是否遇到限流=limit_hit,
        候选票路径=默认候选输出路径,
        待校对路径=review_path,
        HTML路径=默认HTML路径,
        失败清单路径=failure_path,
        今日候选票数量=candidate_count,
        等级分布=grade_distribution,
        top20=top20,
        qqq存在=qqq_exists,
        spy存在=spy_exists,
        html已生成=html_generated,
        dry_run=args.dry_run,
        skip_download=args.skip_download,
        skip_html=args.skip_html,
        严重问题=severe_issues,
    )
    默认验证报告路径.write_text(生成真实候选池验证报告(context), encoding="utf-8")
    return context


def 生成严重问题(
    qqq_exists: bool,
    spy_exists: bool,
    cache_before: int,
    cache_after: int,
    attempted: int,
    success: int,
    failure: int,
    candidate_count: int,
    html_generated: bool,
    dry_run: bool,
    skip_html: bool,
) -> list[str]:
    """生成真实验证严重问题清单。"""
    issues: list[str] = []
    if not qqq_exists:
        issues.append("QQQ 缺失")
    if not spy_exists:
        issues.append("SPY 缺失")
    if not dry_run and cache_after <= cache_before and cache_before < 50:
        issues.append("下载后缓存数量没有增加，且已有缓存不足50")
    if not dry_run and candidate_count == 0:
        issues.append("候选票数量为0")
    if not dry_run and not skip_html and not html_generated:
        issues.append("HTML 没生成")
    if not dry_run and attempted > 0 and success == 0 and failure > 0:
        issues.append("全部下载失败")
    if dry_run:
        issues.append("dry-run 模式未执行真实下载")
    return issues


def 生成真实候选池验证报告(context: 真实验证上下文) -> str:
    """生成真实候选池验证报告。"""
    recommendation = "可以进入第 12 步人工校对闭环" if not context.严重问题 else "不建议进入第 12 步人工校对闭环"
    lines = [
        "# 真实候选池验证报告",
        "",
        f"1. 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"2. 目标候选池规模：{context.目标候选池规模}",
        f"3. 实际下载候选池数量：{context.候选池数量}",
        f"4. 下载候选池路径：`{context.候选池路径}`",
        f"5. 下载前缓存文件数量：{context.下载前缓存数量}",
        f"6. 下载后缓存文件数量：{context.下载后缓存数量}",
        f"7. 本轮尝试下载数量：{context.尝试下载数量}",
        f"8. 本轮成功下载数量：{context.成功下载数量}",
        f"9. 本轮失败下载数量：{context.失败下载数量}",
        f"10. provider 使用情况：{context.provider}",
        f"11. 是否遇到限流：{'是' if context.是否遇到限流 else '否'}",
        f"12. 候选票输出路径：`{context.候选票路径}`",
        f"13. 待校对文件路径：`{context.待校对路径}`",
        f"14. HTML 报告路径：`{context.HTML路径}`",
        f"15. 今日候选票数量：{context.今日候选票数量}",
        "16. 等级分布：",
    ]
    if context.等级分布:
        for grade, count in context.等级分布.items():
            lines.append(f"    - {grade}：{count}")
    else:
        lines.append("    - 无")
    lines.extend(
        [
            f"17. A+ 数量：{context.等级分布.get('A+', 0)}",
            f"18. A 数量：{context.等级分布.get('A', 0)}",
            f"19. B 数量：{context.等级分布.get('B', 0)}",
            "20. Top 20 摘要：",
        ]
    )
    if context.top20.empty:
        lines.append("    - 无")
    else:
        for _, row in context.top20.iterrows():
            lines.append(f"    - {格式化候选摘要行(row)}")
    lines.extend(
        [
            f"21. 失败清单路径：`{context.失败清单路径}`",
            "22. 当前结果是否仍受样本范围限制：是，当前结果只基于已缓存或本轮已下载标的，不代表全市场。",
            "23. 是否建议进入第 12 步“人工校对闭环”：",
            f"    - {recommendation}",
            "",
            "## 运行模式",
            "",
            f"- dry-run：{'是' if context.dry_run else '否'}",
            f"- skip-download：{'是' if context.skip_download else '否'}",
            f"- skip-html：{'是' if context.skip_html else '否'}",
            "- 验证种子列表只用于扩大样本覆盖，不是交易推荐，也不会获得评分加分。",
            "- 本系统只做候选票筛选和复盘辅助，不自动交易，不给确定性买卖建议。",
            "",
            "## 严重问题",
            "",
        ]
    )
    if context.严重问题:
        lines.extend(f"- {issue}" for issue in context.严重问题)
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def main() -> int:
    """命令行入口。"""
    args = parse_args()
    logger = get_logger("Mstock真实验证")
    try:
        context = 运行真实数据验证(args)
    except Exception as exc:
        logger.error(f"真实候选池验证失败：{exc}")
        return 1

    logger.info(f"下载候选池路径：{context.候选池路径}")
    logger.info(f"下载前缓存数量：{context.下载前缓存数量}，下载后缓存数量：{context.下载后缓存数量}")
    logger.info(f"尝试下载数量：{context.尝试下载数量}，成功：{context.成功下载数量}，失败：{context.失败下载数量}")
    logger.info(f"真实候选池验证报告已生成：{默认验证报告路径}")
    if context.严重问题:
        logger.warning(f"验证存在严重问题：{'；'.join(context.严重问题)}")
    else:
        logger.info("验证未发现严重问题，可以进入第 12 步人工校对闭环。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
