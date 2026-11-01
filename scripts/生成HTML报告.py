"""生成中文 HTML 候选票报告。"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from src.reports.html_report import 生成HTML报告  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


默认输入路径 = 项目根目录 / "data" / "output" / "今日候选票.csv"
默认缓存目录 = 项目根目录 / "data" / "cache" / "daily"
默认输出路径 = 项目根目录 / "data" / "output" / "今日候选票.html"
默认图表目录 = 项目根目录 / "data" / "output" / "html_assets" / "charts"
默认验收报告路径 = 项目根目录 / "data" / "output" / "HTML报告验收报告.md"
默认失败清单路径 = 项目根目录 / "data" / "output" / "HTML报告失败清单.csv"


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="生成中文 HTML 候选票报告。")
    parser.add_argument("--input", type=str, default=str(默认输入路径), help="候选票 CSV 输入路径。")
    parser.add_argument("--cache-dir", type=str, default=str(默认缓存目录), help="日线缓存目录。")
    parser.add_argument("--output", type=str, default=str(默认输出路径), help="HTML 输出路径。")
    parser.add_argument("--charts-dir", type=str, default=str(默认图表目录), help="图表输出目录。")
    parser.add_argument("--report", type=str, default=str(默认验收报告路径), help="HTML 验收报告路径。")
    parser.add_argument("--top", type=int, default=100, help="最多展示前 N 只，0 表示不限制。")
    parser.add_argument("--min-score", type=float, default=0.0, help="最低综合评分。")
    parser.add_argument("--min-grade", choices=["D", "C", "B", "A", "A+"], default="D", help="最低等级。")
    parser.add_argument("--no-charts", action="store_true", help="不生成 K 线缩略图。")
    parser.add_argument("--open", action="store_true", help="生成后尝试打开 HTML。")
    return parser.parse_args()


def main() -> int:
    """生成 HTML 报告。"""
    args = parse_args()
    logger = get_logger("Mstock HTML报告")
    if args.top < 0:
        logger.error("参数错误：--top 不能小于0。")
        return 1
    if args.min_score < 0 or args.min_score > 100:
        logger.error("参数错误：--min-score 必须在0到100之间。")
        return 1

    try:
        result = 生成HTML报告(
            input_path=args.input,
            cache_dir=args.cache_dir,
            output_path=args.output,
            charts_dir=args.charts_dir,
            report_path=args.report,
            failure_path=默认失败清单路径,
            top=args.top,
            min_score=args.min_score,
            min_grade=args.min_grade,
            no_charts=args.no_charts,
        )
    except Exception as exc:
        logger.error(f"生成 HTML 报告失败：{exc}")
        return 1

    logger.info(f"HTML 报告已生成：{result.html_path}")
    logger.info(f"图表目录：{result.charts_dir}")
    logger.info(f"HTML 验收报告已生成：{result.report_path}")
    logger.info(f"HTML 报告失败清单已生成：{result.failure_path}")
    logger.info(f"展示候选数量：{result.display_count}，图表生成数量：{result.chart_count}，图表失败数量：{result.chart_failure_count}")

    if args.open:
        try:
            webbrowser.open(Path(args.output).resolve().as_uri())
            logger.info("已尝试打开 HTML 报告。")
        except Exception as exc:
            logger.warning(f"自动打开 HTML 失败，请手动打开文件：{args.output}；原因：{exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
