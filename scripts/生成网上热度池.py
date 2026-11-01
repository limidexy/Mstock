"""生成网上热度动态下载池。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from src.data.hot_universe import 生成网上热度池  # noqa: E402
from src.data.web_hot_sources import HotSourceConfig, 默认来源列表  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


默认输出路径 = 项目根目录 / "data" / "processed" / "网上热度池.csv"
默认报告路径 = 项目根目录 / "data" / "output" / "网上热度池生成报告.md"
默认失败路径 = 项目根目录 / "data" / "output" / "网上热度来源失败清单.csv"
默认股票池路径 = 项目根目录 / "data" / "processed" / "美股股票池.csv"
默认缓存目录 = 项目根目录 / "data" / "cache" / "daily"
默认原始缓存目录 = 项目根目录 / "data" / "raw" / "hot_sources"


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="生成网上热度动态下载池。")
    parser.add_argument("--limit", type=int, default=500, help="热度池最多输出数量。")
    parser.add_argument(
        "--sources",
        type=str,
        default=",".join(默认来源列表),
        help="逗号分隔来源键。",
    )
    parser.add_argument("--timeout", type=int, default=15, help="网页请求超时秒数。")
    parser.add_argument("--sleep-min", type=float, default=1.0, help="请求最小间隔秒数。")
    parser.add_argument("--sleep-max", type=float, default=3.0, help="请求最大间隔秒数。")
    parser.add_argument("--max-retries", type=int, default=2, help="单个来源最大重试次数。")
    parser.add_argument("--use-cache", action="store_true", help="缓存每个来源的原始响应。")
    parser.add_argument("--no-network", action="store_true", help="只使用本地缓存计算来源。")
    parser.add_argument("--output", type=str, default=str(默认输出路径), help="网上热度池 CSV 输出路径。")
    parser.add_argument("--report", type=str, default=str(默认报告路径), help="网上热度池报告路径。")
    parser.add_argument("--failure-output", type=str, default=str(默认失败路径), help="来源失败清单路径。")
    parser.add_argument("--cache-dir", type=str, default=str(默认缓存目录), help="日线缓存目录。")
    parser.add_argument("--stock-pool", type=str, default=str(默认股票池路径), help="股票池元数据路径。")
    return parser.parse_args()


def 解析来源列表(source_text: str) -> list[str]:
    """解析逗号分隔来源键。"""
    return [source.strip() for source in source_text.split(",") if source.strip()]


def 运行生成网上热度池(args: argparse.Namespace):
    """执行网上热度池生成。"""
    config = HotSourceConfig(
        timeout=args.timeout,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
        max_retries=args.max_retries,
        use_cache=args.use_cache or not args.no_network,
        no_network=args.no_network,
        raw_cache_dir=默认原始缓存目录,
    )
    return 生成网上热度池(
        source_keys=解析来源列表(args.sources),
        output_path=args.output,
        report_path=args.report,
        failure_path=args.failure_output,
        stock_pool_path=args.stock_pool,
        cache_dir=args.cache_dir,
        limit=args.limit,
        config=config,
        no_network=args.no_network,
        logger=get_logger("Mstock网上热度池"),
    )


def main() -> int:
    """命令行入口。"""
    args = parse_args()
    logger = get_logger("Mstock网上热度池")
    if args.limit <= 0:
        logger.error("参数错误：--limit 必须大于0。")
        return 1
    if args.timeout <= 0:
        logger.error("参数错误：--timeout 必须大于0。")
        return 1
    if args.sleep_min < 0 or args.sleep_max < args.sleep_min:
        logger.error("参数错误：请求间隔必须满足 0 <= sleep-min <= sleep-max。")
        return 1
    if args.max_retries < 0:
        logger.error("参数错误：--max-retries 不能小于0。")
        return 1

    try:
        result = 运行生成网上热度池(args)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"生成网上热度池失败：{exc}")
        return 1

    logger.info(f"网上热度池已生成：{result.输出路径}")
    logger.info(f"网上热度池数量：{len(result.数据)}")
    logger.info(f"来源成功数量：{result.来源成功数量}，来源失败数量：{result.来源失败数量}")
    logger.info(f"生成报告：{result.报告路径}")
    logger.info(f"来源失败清单：{result.失败清单路径}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
