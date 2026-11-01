"""构建扩大真实数据验证用的下载候选池。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from src.data.universe_selection import 最大自动候选池规模, 构建下载候选池, 生成候选池构建报告  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


默认股票池路径 = 项目根目录 / "data" / "processed" / "美股股票池.csv"
默认报告路径 = 项目根目录 / "data" / "output" / "下载候选池构建报告.md"


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="构建下载候选池。")
    parser.add_argument("--target-size", type=int, default=200, help="目标候选池规模，默认200，最大500。")
    parser.add_argument("--stock-pool", type=str, default=str(默认股票池路径), help="美股股票池路径。")
    parser.add_argument("--output", type=str, default=None, help="下载候选池输出路径。")
    parser.add_argument("--report", type=str, default=str(默认报告路径), help="下载候选池构建报告路径。")
    return parser.parse_args()


def main() -> int:
    """运行下载候选池构建。"""
    args = parse_args()
    logger = get_logger("Mstock下载候选池")
    if args.target_size <= 0:
        logger.error("参数错误：--target-size 必须大于0。")
        return 1
    if args.target_size > 最大自动候选池规模:
        logger.error("目标规模超过500，本轮不会自动构建或下载；请先完成200规模验证后再扩大。")
        return 1

    output_path = Path(args.output) if args.output else 项目根目录 / "data" / "processed" / f"下载候选池_{args.target_size}.csv"
    report_path = Path(args.report)
    try:
        result = 构建下载候选池(args.stock_pool, target_size=args.target_size, output_path=output_path)
        report = 生成候选池构建报告(result)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    except Exception as exc:
        logger.error(f"下载候选池构建失败：{exc}")
        return 1

    logger.info(f"下载候选池已生成：{result.输出路径}")
    logger.info(f"下载候选池数量：{len(result.数据)}")
    logger.info(f"下载候选池构建报告已生成：{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
