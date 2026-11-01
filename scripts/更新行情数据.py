"""更新日线行情数据。

支持从中文股票池读取代码，使用 yfinance / Stooq 下载日线 OHLCV，并按单只标的缓存。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from src.data.cache import 导入手动CSV, 批量更新日线缓存, 读取失败代码, 统计缓存文件数量, 选择下载代码  # noqa: E402
from src.data.providers import 自动行情数据源  # noqa: E402
from src.data.stooq_provider import StooqProvider  # noqa: E402
from src.data.yfinance_provider import YFinanceProvider  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="更新美股 / ETF 日线行情缓存。")
    parser.add_argument("--limit", type=int, default=50, help="从股票池前 N 只开始下载；传入 0 表示全量。")
    parser.add_argument("--days", type=int, default=300, help="每只标的默认保留最近 N 个交易日。")
    parser.add_argument("--tickers", type=str, default=None, help="逗号分隔代码，例如 AAPL,MSFT,QQQ,SPY。")
    parser.add_argument("--force", action="store_true", help="强制全量刷新已有缓存。")
    parser.add_argument("--provider", choices=["yfinance", "stooq", "auto"], default="auto", help="行情数据源。")
    parser.add_argument("--sleep-min", type=float, default=1.0, help="两次请求之间的最小等待秒数。")
    parser.add_argument("--sleep-max", type=float, default=3.0, help="两次请求之间的最大等待秒数。")
    parser.add_argument("--max-retries", type=int, default=2, help="单只标的下载失败后的最大重试次数。")
    parser.add_argument("--retry-failed", action="store_true", help="只重试下载失败清单中的代码。")
    parser.add_argument("--import-csv", type=str, default=None, help="导入手动日线CSV文件或目录。")
    parser.add_argument("--import-ticker", type=str, default=None, help="手动CSV缺少代码列时使用的代码。")
    parser.add_argument("--stooq-api-key", type=str, default=None, help="Stooq API key；也可使用环境变量 STOOQ_API_KEY。")
    return parser.parse_args()


def 创建数据源(provider_name: str, stooq_api_key: str | None = None):
    """创建行情数据源。"""
    stooq_key = stooq_api_key or os.getenv("STOOQ_API_KEY")
    if provider_name == "yfinance":
        return YFinanceProvider()
    if provider_name == "stooq":
        return StooqProvider(api_key=stooq_key)
    return 自动行情数据源([YFinanceProvider(), StooqProvider(api_key=stooq_key)])


def main() -> int:
    """运行行情更新任务。"""
    args = parse_args()
    logger = get_logger("Mstock行情")

    if args.days <= 0:
        logger.error("参数错误：--days 必须大于0。")
        return 1
    if args.limit < 0:
        logger.error("参数错误：--limit 不能小于0。")
        return 1
    if args.sleep_min < 0 or args.sleep_max < 0:
        logger.error("参数错误：--sleep-min 和 --sleep-max 不能小于0。")
        return 1
    if args.sleep_max < args.sleep_min:
        logger.error("参数错误：--sleep-max 不能小于 --sleep-min。")
        return 1
    if args.max_retries < 0:
        logger.error("参数错误：--max-retries 不能小于0。")
        return 1

    stock_pool_path = 项目根目录 / "data" / "processed" / "美股股票池.csv"
    cache_dir = 项目根目录 / "data" / "cache"
    failure_path = 项目根目录 / "data" / "output" / "下载失败清单.csv"
    limit = None if args.limit == 0 else args.limit

    if args.import_csv:
        try:
            results = 导入手动CSV(
                args.import_csv,
                cache_dir=cache_dir,
                days=args.days,
                ticker=args.import_ticker,
            )
        except Exception as exc:
            logger.error(f"手动CSV导入失败：{exc}")
            return 1

        logger.info(f"手动CSV导入成功数量：{len(results)}")
        for result in results:
            logger.info(f"{result.代码} 导入成功：{result.缓存路径}")
        logger.info(f"当前缓存文件数量：{统计缓存文件数量(cache_dir)}")
        return 0

    try:
        if args.retry_failed:
            tickers = 读取失败代码(failure_path)
            logger.info(f"启用失败重试模式，读取失败代码数量：{len(tickers)}")
        else:
            tickers = 选择下载代码(stock_pool_path, limit=limit, tickers=args.tickers)
    except Exception as exc:
        logger.error(f"选择下载代码失败：{exc}")
        return 1

    logger.info(f"计划下载代码数量：{len(tickers)}")
    logger.info(f"默认交易日数量：{args.days}")
    logger.info(f"是否强制刷新：{'是' if args.force else '否'}")
    logger.info(f"行情数据源：{args.provider}")
    logger.info(f"请求间隔：{args.sleep_min:.1f} 到 {args.sleep_max:.1f} 秒")
    logger.info(f"最大重试次数：{args.max_retries}")

    provider = 创建数据源(args.provider, stooq_api_key=args.stooq_api_key)
    result = 批量更新日线缓存(
        provider=provider,
        tickers=tickers,
        cache_dir=cache_dir,
        days=args.days,
        force=args.force,
        failure_path=failure_path,
        max_retries=args.max_retries,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
        logger=logger,
    )

    cache_count = 统计缓存文件数量(cache_dir)
    logger.info(f"行情更新成功数量：{result.成功数量}")
    logger.info(f"行情更新失败数量：{result.失败数量}")
    logger.info(f"下载失败清单路径：{result.失败清单路径}")
    logger.info(f"当前缓存文件数量：{cache_count}")

    return 0 if result.失败数量 == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
