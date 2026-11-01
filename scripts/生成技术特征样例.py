"""生成技术特征样例。

只读取 data/cache/daily/ 中已有缓存，不联网、不下载行情、不生成候选票。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from src.features.breakout import 添加突破特征  # noqa: E402
from src.features.macd import 添加MACD特征  # noqa: E402
from src.features.moving_average import 添加均线特征  # noqa: E402
from src.features.relative_strength import 添加相对强度特征  # noqa: E402
from src.features.required_columns import 基准代码, get_missing_feature_columns, get_required_feature_columns  # noqa: E402
from src.features.risk import 添加风险特征  # noqa: E402
from src.features.volume import 添加量能特征  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="生成技术特征样例。")
    parser.add_argument("--limit", type=int, default=20, help="输出样例股票数量，不包含 QQQ/SPY。")
    parser.add_argument("--cache-dir", type=str, default=str(项目根目录 / "data" / "cache" / "daily"), help="日线缓存目录。")
    parser.add_argument("--output", type=str, default=str(项目根目录 / "data" / "output" / "技术特征样例.csv"), help="样例输出路径。")
    return parser.parse_args()


def 计算单票特征(df: pd.DataFrame, qqq: pd.DataFrame, spy: pd.DataFrame) -> pd.DataFrame:
    """计算单只股票的完整技术特征。"""
    features = 添加均线特征(df)
    features = 添加MACD特征(features)
    features = 添加量能特征(features)
    features = 添加突破特征(features)
    features = 添加风险特征(features)
    features = 添加相对强度特征(features, qqq, spy)
    return features


def main() -> int:
    """生成样例文件。"""
    args = parse_args()
    logger = get_logger("Mstock技术特征样例")
    cache_dir = Path(args.cache_dir)
    output_path = Path(args.output)

    if args.limit <= 0:
        logger.error("参数错误：--limit 必须大于0。")
        return 1
    if not cache_dir.exists():
        logger.error(f"日线缓存目录不存在：{cache_dir}")
        return 1

    qqq_path = cache_dir / "QQQ.csv"
    spy_path = cache_dir / "SPY.csv"
    if not qqq_path.exists() or not spy_path.exists():
        logger.error("生成样例失败：缺少 QQQ.csv 或 SPY.csv 基准缓存。")
        return 1

    qqq = pd.read_csv(qqq_path, encoding="utf-8-sig")
    spy = pd.read_csv(spy_path, encoding="utf-8-sig")
    required_columns = get_required_feature_columns()
    rows = []
    errors = []

    for path in sorted(cache_dir.glob("*.csv")):
        ticker = path.stem.upper()
        if ticker in set(基准代码):
            continue
        if len(rows) >= args.limit:
            break
        try:
            daily = pd.read_csv(path, encoding="utf-8-sig")
            features = 计算单票特征(daily, qqq, spy)
            missing = get_missing_feature_columns(features.columns.tolist())
            if missing:
                errors.append(f"{ticker} 缺少字段：{'、'.join(missing)}")
                continue
            rows.append(features.tail(1)[required_columns])
        except Exception as exc:
            errors.append(f"{ticker} 特征计算失败：{exc}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sample = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=required_columns)
    sample.to_csv(output_path, index=False, encoding="utf-8-sig")

    logger.info(f"技术特征样例已生成：{output_path}")
    logger.info(f"样例行数：{len(sample)}")
    logger.info(f"样例字段数：{len(sample.columns)}")
    logger.info("默认已排除 QQQ、SPY。")

    if errors:
        logger.error(f"存在特征计算错误，错误数量：{len(errors)}")
        for error in errors[:10]:
            logger.error(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
