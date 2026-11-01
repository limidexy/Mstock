"""更新网上热度池中的日线行情缓存。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
from pathlib import Path

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from scripts.更新行情数据 import 创建数据源  # noqa: E402
from src.data.cache import 批量更新日线缓存, 保存失败清单, 日线缓存路径, 去重保序  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


默认热度池路径 = 项目根目录 / "data" / "processed" / "网上热度池.csv"
默认缓存根目录 = 项目根目录 / "data" / "cache"
默认失败路径 = 项目根目录 / "data" / "output" / "网上热度池下载失败清单.csv"
基准代码 = ["QQQ", "SPY"]


@dataclass(frozen=True)
class 网上热度池行情更新结果:
    """网上热度池行情更新结果。"""

    热度池路径: Path
    计划代码数量: int
    本轮尝试下载数量: int
    下载成功数量: int
    下载失败数量: int
    失败清单路径: Path
    provider: str


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="更新网上热度池行情缓存。")
    parser.add_argument("--days", type=int, default=300, help="下载最近交易日数量。")
    parser.add_argument("--provider", choices=["yfinance", "stooq", "auto"], default="auto", help="行情数据源。")
    parser.add_argument("--sleep-min", type=float, default=0.5, help="请求最小间隔秒数。")
    parser.add_argument("--sleep-max", type=float, default=1.5, help="请求最大间隔秒数。")
    parser.add_argument("--max-retries", type=int, default=2, help="单只标的最大重试次数。")
    parser.add_argument("--limit", type=int, default=500, help="热度池前 N 只，QQQ/SPY 会被保留。")
    parser.add_argument("--missing-only", action="store_true", help="只下载缺失缓存的代码。")
    parser.add_argument("--force", action="store_true", help="强制刷新已有缓存。")
    parser.add_argument("--pool", type=str, default=str(默认热度池路径), help="网上热度池 CSV 路径。")
    parser.add_argument("--failure-output", type=str, default=str(默认失败路径), help="下载失败清单路径。")
    return parser.parse_args()


def 读取热度池代码(pool_path: Path | str, limit: int = 500) -> list[str]:
    """读取热度池代码，并确保 QQQ、SPY 保留。"""
    path = Path(pool_path)
    if not path.exists():
        raise FileNotFoundError(f"网上热度池文件不存在：{path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "代码" not in df.columns:
        raise ValueError(f"网上热度池字段缺失：代码，文件：{path}")
    codes = df["代码"].dropna().astype(str).str.upper().tolist()
    if limit > 0:
        codes = codes[:limit]
    return 去重保序(基准代码 + codes)


def 过滤缺失缓存代码(codes: list[str], cache_root: Path | str) -> list[str]:
    """只保留缺失日线缓存的代码。"""
    cache_root = Path(cache_root)
    return [code for code in codes if not 日线缓存路径(cache_root, code).exists()]


def 运行更新网上热度池行情(args: argparse.Namespace) -> 网上热度池行情更新结果:
    """执行网上热度池行情更新。"""
    if args.days <= 0:
        raise ValueError("参数错误：--days 必须大于0。")
    if args.limit < 0:
        raise ValueError("参数错误：--limit 不能小于0。")
    if args.sleep_min < 0 or args.sleep_max < args.sleep_min:
        raise ValueError("参数错误：请求间隔必须满足 0 <= sleep-min <= sleep-max。")
    if args.max_retries < 0:
        raise ValueError("参数错误：--max-retries 不能小于0。")

    codes = 读取热度池代码(args.pool, limit=args.limit)
    download_codes = codes
    if args.missing_only and not args.force:
        download_codes = 过滤缺失缓存代码(codes, 默认缓存根目录)

    if not download_codes:
        failure_path = 保存失败清单([], args.failure_output)
        return 网上热度池行情更新结果(
            热度池路径=Path(args.pool),
            计划代码数量=len(codes),
            本轮尝试下载数量=0,
            下载成功数量=0,
            下载失败数量=0,
            失败清单路径=failure_path,
            provider=args.provider,
        )

    provider = 创建数据源(args.provider)
    result = 批量更新日线缓存(
        provider=provider,
        tickers=download_codes,
        cache_dir=默认缓存根目录,
        days=args.days,
        force=args.force,
        failure_path=args.failure_output,
        max_retries=args.max_retries,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
        logger=get_logger("Mstock网上热度行情"),
    )
    return 网上热度池行情更新结果(
        热度池路径=Path(args.pool),
        计划代码数量=len(codes),
        本轮尝试下载数量=len(download_codes),
        下载成功数量=result.成功数量,
        下载失败数量=result.失败数量,
        失败清单路径=result.失败清单路径,
        provider=args.provider,
    )


def main() -> int:
    """命令行入口。"""
    args = parse_args()
    logger = get_logger("Mstock网上热度行情")
    try:
        result = 运行更新网上热度池行情(args)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"更新网上热度池行情失败：{exc}")
        return 1

    logger.info(f"热度池路径：{result.热度池路径}")
    logger.info(f"计划覆盖代码数量：{result.计划代码数量}")
    logger.info(f"本轮尝试下载数量：{result.本轮尝试下载数量}")
    logger.info(f"下载成功数量：{result.下载成功数量}")
    logger.info(f"下载失败数量：{result.下载失败数量}")
    logger.info(f"下载失败清单路径：{result.失败清单路径}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
