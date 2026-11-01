"""日线行情缓存与批量更新。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import random
import re
import time

import pandas as pd

from src.data.providers import 日线行情数据源, 行情下载错误, 校验行情字段


日线缓存字段 = [
    "日期",
    "代码",
    "开盘价",
    "最高价",
    "最低价",
    "收盘价",
    "复权收盘价",
    "成交量",
    "数据来源",
    "更新时间",
]

失败清单字段 = ["代码", "失败原因", "更新时间"]
基准代码 = ["QQQ", "SPY"]


@dataclass(frozen=True)
class 单只更新结果:
    """单只标的缓存更新结果。"""

    代码: str
    成功: bool
    缓存路径: Path | None
    行数: int
    信息: str


@dataclass(frozen=True)
class 批量更新结果:
    """批量行情更新结果。"""

    成功清单: list[单只更新结果]
    失败清单: list[dict[str, str]]
    失败清单路径: Path

    @property
    def 成功数量(self) -> int:
        """返回成功数量。"""
        return len(self.成功清单)

    @property
    def 失败数量(self) -> int:
        """返回失败数量。"""
        return len(self.失败清单)


def 读取股票池(path: Path | str) -> pd.DataFrame:
    """读取处理后的中文股票池。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"股票池文件不存在：{path}")

    df = pd.read_csv(path, encoding="utf-8-sig")
    required_columns = ["代码", "名称", "市场", "是否ETF"]
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"股票池字段缺失：{missing}")
    if df.empty:
        raise ValueError(f"股票池为空：{path}")
    return df


def 解析代码列表(tickers: str | None) -> list[str]:
    """解析命令行传入的逗号分隔代码。"""
    if not tickers:
        return []
    return 去重保序([ticker.strip().upper() for ticker in tickers.split(",") if ticker.strip()])


def 去重保序(tickers: list[str]) -> list[str]:
    """保持顺序去重。"""
    seen = set()
    result = []
    for ticker in tickers:
        normalized = ticker.strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def 添加基准代码(tickers: list[str]) -> list[str]:
    """确保 QQQ 和 SPY 作为相对强度基准被下载。"""
    return 去重保序(基准代码 + tickers)


def 选择下载代码(
    股票池路径: Path | str,
    limit: int | None = 50,
    tickers: str | None = None,
) -> list[str]:
    """根据参数选择需要下载的代码。"""
    指定代码 = 解析代码列表(tickers)
    if 指定代码:
        return 添加基准代码(指定代码)

    stock_pool = 读取股票池(股票池路径)
    pool_tickers = stock_pool["代码"].dropna().astype(str).str.upper().tolist()
    if limit is not None and limit > 0:
        pool_tickers = pool_tickers[:limit]
    return 添加基准代码(pool_tickers)


def 读取失败代码(failure_path: Path | str) -> list[str]:
    """从中文失败清单中读取需要重试的代码。"""
    failure_path = Path(failure_path)
    if not failure_path.exists():
        raise FileNotFoundError(f"失败清单不存在：{failure_path}")

    df = pd.read_csv(failure_path, encoding="utf-8-sig")
    if "代码" not in df.columns:
        raise ValueError(f"失败清单字段缺失：代码，文件：{failure_path}")
    codes = df["代码"].dropna().astype(str).str.upper().tolist()
    if not codes:
        raise ValueError(f"失败清单没有可重试代码：{failure_path}")
    return 添加基准代码(codes)


def 代码转缓存文件名(ticker: str) -> str:
    """把交易代码转换为安全的缓存文件名。"""
    normalized = ticker.strip().upper()
    return re.sub(r"[^A-Z0-9.\-]+", "-", normalized) + ".csv"


def 日线缓存路径(cache_dir: Path | str, ticker: str) -> Path:
    """返回单只标的日线缓存路径。"""
    return Path(cache_dir) / "daily" / 代码转缓存文件名(ticker)


def 读取日线缓存(path: Path) -> pd.DataFrame:
    """读取单只标的日线缓存。"""
    if not path.exists():
        return pd.DataFrame(columns=日线缓存字段)
    df = pd.read_csv(path, encoding="utf-8-sig")
    校验行情字段(df, str(path))
    return df[日线缓存字段].sort_values("日期").reset_index(drop=True)


def 保存日线缓存(df: pd.DataFrame, path: Path, days: int) -> Path:
    """保存单只标的日线缓存。"""
    校验行情字段(df, str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    output = df[日线缓存字段].drop_duplicates(subset=["日期"], keep="last")
    output = output.sort_values("日期").tail(days).reset_index(drop=True)
    output.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def 合并日线缓存(existing: pd.DataFrame, new_data: pd.DataFrame, days: int) -> pd.DataFrame:
    """合并已有缓存和新增行情。"""
    frames = [frame for frame in [existing, new_data] if not frame.empty]
    if not frames:
        raise 行情下载错误("合并行情失败：没有可用数据。")
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["日期"], keep="last")
    return combined.sort_values("日期").tail(days).reset_index(drop=True)


def 是否临时限流错误(message: str) -> bool:
    """判断错误信息是否像临时限流。"""
    keywords = ["限流", "Too Many Requests", "Rate limited", "YFRateLimitError", "请求过于频繁"]
    return any(keyword in message for keyword in keywords)


def 计算等待秒数(attempt: int, sleep_min: float, sleep_max: float) -> float:
    """计算指数退避等待时间，并加入随机抖动。"""
    if sleep_min <= 0 and sleep_max <= 0:
        return 0.0
    lower = max(0.0, sleep_min)
    upper = max(lower, sleep_max)
    jitter = random.uniform(lower, upper)
    return jitter * (2 ** max(0, attempt - 1))


def 等待一段时间(seconds: float, logger=None, message: str | None = None) -> None:
    """按需等待，测试可通过传入0跳过。"""
    if seconds <= 0:
        return
    if logger and message:
        logger.info(f"{message}，等待 {seconds:.1f} 秒。")
    time.sleep(seconds)


def 下载日线带重试(
    provider: 日线行情数据源,
    ticker: str,
    days: int,
    start=None,
    max_retries: int = 0,
    sleep_min: float = 0.0,
    sleep_max: float = 0.0,
    logger=None,
) -> pd.DataFrame:
    """下载单只日线行情，支持指数退避重试。"""
    attempts = max_retries + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return provider.download_daily(ticker, days=days, start=start)
        except Exception as exc:
            last_error = exc
            message = str(exc)
            if attempt >= attempts:
                break

            retry_index = attempt
            wait_seconds = 计算等待秒数(retry_index, sleep_min, sleep_max)
            if logger:
                if 是否临时限流错误(message):
                    logger.warning(f"{ticker} 遇到临时限流，第{retry_index}次重试前等待。原始错误：{message}")
                else:
                    logger.warning(f"{ticker} 下载失败，准备第{retry_index}次重试。原始错误：{message}")
            等待一段时间(wait_seconds, logger=logger, message=f"{ticker} 第{retry_index}次重试")

    raise 行情下载错误(f"{ticker} 多次下载失败：{last_error}")


def 更新单只日线缓存(
    provider: 日线行情数据源,
    ticker: str,
    cache_dir: Path | str,
    days: int = 300,
    force: bool = False,
    max_retries: int = 0,
    sleep_min: float = 0.0,
    sleep_max: float = 0.0,
    logger=None,
) -> 单只更新结果:
    """更新单只标的日线缓存，支持增量更新。"""
    path = 日线缓存路径(cache_dir, ticker)

    if force or not path.exists():
        data = 下载日线带重试(
            provider,
            ticker,
            days=days,
            max_retries=max_retries,
            sleep_min=sleep_min,
            sleep_max=sleep_max,
            logger=logger,
        )
        保存日线缓存(data, path, days=days)
        return 单只更新结果(ticker, True, path, len(data), "全量缓存已更新")

    existing = 读取日线缓存(path)
    last_date = pd.to_datetime(existing["日期"]).max().date()
    start = last_date + timedelta(days=1)

    try:
        new_data = 下载日线带重试(
            provider,
            ticker,
            days=days,
            start=start,
            max_retries=max_retries,
            sleep_min=sleep_min,
            sleep_max=sleep_max,
            logger=logger,
        )
    except 行情下载错误 as exc:
        message = str(exc)
        if "没有返回行情数据" in message or "没有可用行情数据" in message:
            保存日线缓存(existing, path, days=days)
            return 单只更新结果(ticker, True, path, len(existing), "没有新增行情，保留现有缓存")
        raise

    combined = 合并日线缓存(existing, new_data, days=days)
    保存日线缓存(combined, path, days=days)
    return 单只更新结果(ticker, True, path, len(combined), "增量缓存已更新")


def 保存失败清单(failures: list[dict[str, str]], output_path: Path | str) -> Path:
    """保存行情下载失败清单。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(failures, columns=失败清单字段)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def 批量更新日线缓存(
    provider: 日线行情数据源,
    tickers: list[str],
    cache_dir: Path | str = Path("data/cache"),
    days: int = 300,
    force: bool = False,
    failure_path: Path | str = Path("data/output/下载失败清单.csv"),
    max_retries: int = 0,
    sleep_min: float = 0.0,
    sleep_max: float = 0.0,
    logger=None,
) -> 批量更新结果:
    """批量更新日线缓存，并记录失败清单。"""
    成功清单: list[单只更新结果] = []
    失败清单: list[dict[str, str]] = []
    更新时间 = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S")

    for index, ticker in enumerate(去重保序(tickers), start=1):
        if index > 1:
            interval_seconds = 计算等待秒数(1, sleep_min, sleep_max)
            等待一段时间(interval_seconds, logger=logger, message="请求间隔")
        if logger:
            provider_name = getattr(provider, "数据源名称", provider.__class__.__name__)
            logger.info(f"正在下载日线行情：{ticker}（{index}/{len(tickers)}，数据源：{provider_name}）")
        try:
            result = 更新单只日线缓存(
                provider,
                ticker,
                cache_dir=cache_dir,
                days=days,
                force=force,
                max_retries=max_retries,
                sleep_min=sleep_min,
                sleep_max=sleep_max,
                logger=logger,
            )
            成功清单.append(result)
            if logger:
                logger.info(f"{ticker} 下载成功：{result.信息}，缓存行数：{result.行数}")
        except Exception as exc:
            failure = {"代码": ticker, "失败原因": f"{ticker} 行情下载失败：{exc}", "更新时间": 更新时间}
            失败清单.append(failure)
            if logger:
                logger.error(f"{failure['失败原因']}。下载失败，已记录。")

    failure_output_path = 保存失败清单(失败清单, failure_path)
    return 批量更新结果(成功清单=成功清单, 失败清单=失败清单, 失败清单路径=failure_output_path)


def 统计缓存文件数量(cache_dir: Path | str = Path("data/cache")) -> int:
    """统计日线缓存 CSV 文件数量。"""
    daily_dir = Path(cache_dir) / "daily"
    if not daily_dir.exists():
        return 0
    return len(list(daily_dir.glob("*.csv")))


手动CSV字段映射 = {
    "date": "日期",
    "日期": "日期",
    "open": "开盘价",
    "开盘价": "开盘价",
    "high": "最高价",
    "最高价": "最高价",
    "low": "最低价",
    "最低价": "最低价",
    "close": "收盘价",
    "收盘价": "收盘价",
    "adj close": "复权收盘价",
    "adj_close": "复权收盘价",
    "复权收盘价": "复权收盘价",
    "volume": "成交量",
    "成交量": "成交量",
    "ticker": "代码",
    "symbol": "代码",
    "代码": "代码",
}


def 标准化手动CSV(df: pd.DataFrame, ticker: str | None = None) -> pd.DataFrame:
    """把手动导入 CSV 标准化为项目日线缓存字段。"""
    rename_map = {}
    for column in df.columns:
        normalized = str(column).strip().lower()
        if normalized in 手动CSV字段映射:
            rename_map[column] = 手动CSV字段映射[normalized]
    normalized_df = df.rename(columns=rename_map).copy()

    required = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量"]
    missing = [column for column in required if column not in normalized_df.columns]
    if missing:
        raise ValueError(f"手动CSV字段缺失：{missing}")

    if "代码" not in normalized_df.columns:
        if not ticker:
            raise ValueError("手动CSV缺少代码字段，请提供 --import-ticker。")
        normalized_df["代码"] = ticker.strip().upper()
    else:
        normalized_df["代码"] = normalized_df["代码"].astype(str).str.upper()

    if "复权收盘价" not in normalized_df.columns:
        normalized_df["复权收盘价"] = normalized_df["收盘价"]

    normalized_df["日期"] = pd.to_datetime(normalized_df["日期"]).dt.strftime("%Y-%m-%d")
    normalized_df["数据来源"] = "手动CSV"
    normalized_df["更新时间"] = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S")
    normalized_df = normalized_df[日线缓存字段].sort_values(["代码", "日期"]).reset_index(drop=True)

    校验行情字段(normalized_df, ticker or "手动CSV")
    return normalized_df


def 导入单个手动CSV(
    csv_path: Path | str,
    cache_dir: Path | str = Path("data/cache"),
    days: int = 300,
    ticker: str | None = None,
) -> list[单只更新结果]:
    """导入单个手动 CSV 到日线缓存。"""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"手动CSV文件不存在：{csv_path}")

    fallback_ticker = ticker or csv_path.stem.upper()
    df = pd.read_csv(csv_path)
    normalized = 标准化手动CSV(df, ticker=fallback_ticker)
    results: list[单只更新结果] = []

    for code, group in normalized.groupby("代码", sort=True):
        path = 日线缓存路径(cache_dir, str(code))
        保存日线缓存(group.reset_index(drop=True), path, days=days)
        results.append(单只更新结果(str(code), True, path, len(group), "手动CSV已导入"))

    return results


def 导入手动CSV(
    import_path: Path | str,
    cache_dir: Path | str = Path("data/cache"),
    days: int = 300,
    ticker: str | None = None,
) -> list[单只更新结果]:
    """导入手动 CSV 文件或目录。"""
    import_path = Path(import_path)
    if import_path.is_dir():
        results: list[单只更新结果] = []
        files = sorted(import_path.glob("*.csv"))
        if not files:
            raise FileNotFoundError(f"手动CSV目录没有CSV文件：{import_path}")
        for file_path in files:
            results.extend(导入单个手动CSV(file_path, cache_dir=cache_dir, days=days))
        return results

    return 导入单个手动CSV(import_path, cache_dir=cache_dir, days=days, ticker=ticker)
