"""更新美股 / ETF 股票池。

脚本会从 Nasdaq Trader symbol directory 下载 Nasdaq-listed 和 other-listed 清单，
缓存原始文件到 data/raw，并输出处理后的中文股票池 CSV。
"""

from __future__ import annotations

import sys
from pathlib import Path


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from src.data.universe import 股票池下载错误, 更新股票池  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


def main() -> int:
    """运行股票池更新任务。"""
    logger = get_logger("Mstock股票池")
    raw_dir = 项目根目录 / "data" / "raw"
    output_path = 项目根目录 / "data" / "processed" / "美股股票池.csv"

    try:
        logger.info("开始更新美股股票池。")
        result = 更新股票池(raw_dir=raw_dir, output_path=output_path)
    except 股票池下载错误 as exc:
        logger.error(str(exc))
        return 1
    except Exception as exc:  # pragma: no cover
        logger.error(f"更新美股股票池失败：{exc}")
        return 1

    logger.info(f"股票池数量：{result.股票池数量}")
    logger.info(f"ETF数量：{result.ETF数量}")
    logger.info(f"普通股票数量：{result.普通股票数量}")
    logger.info(f"输出文件路径：{result.输出路径}")
    logger.info("美股股票池更新完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
