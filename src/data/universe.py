"""美股 / ETF 股票池下载、解析与过滤。

数据来源为 Nasdaq Trader symbol directory。模块默认只在显式调用下载函数时联网，
所有网络请求都必须设置超时。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
import re
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import requests


NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
默认请求超时秒数 = 30

股票池字段 = [
    "代码",
    "名称",
    "市场",
    "是否ETF",
    "是否测试证券",
    "数据来源",
    "更新时间",
]

非普通标的关键词 = [
    "warrant",
    "warrants",
    "right",
    "rights",
    "unit",
    "units",
    "preferred",
    "preference",
    "depositary share",
    "depositary shares",
    "senior note",
    "senior notes",
    "note due",
    "notes due",
    "debenture",
    "debentures",
    "bond",
    "bonds",
    "contingent value right",
    "cvr",
    "purchase contract",
    "subscription",
]

纳斯达克市场映射 = {
    "Q": "NASDAQ Global Select",
    "G": "NASDAQ Global Market",
    "S": "NASDAQ Capital Market",
}

其他市场映射 = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
}


class 股票池下载错误(RuntimeError):
    """股票池下载失败时抛出的中文异常。"""


@dataclass(frozen=True)
class 股票池结果:
    """股票池生成结果。"""

    数据: pd.DataFrame
    输出路径: Path
    原始文件路径: dict[str, Path]

    @property
    def 股票池数量(self) -> int:
        """返回股票池总数量。"""
        return len(self.数据)

    @property
    def ETF数量(self) -> int:
        """返回 ETF 数量。"""
        return int((self.数据["是否ETF"] == "是").sum())

    @property
    def 普通股票数量(self) -> int:
        """返回普通股票数量。"""
        return int((self.数据["是否ETF"] == "否").sum())


def 当前更新时间() -> str:
    """返回用于输出文件的中文时区更新时间。"""
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")


def 下载文本(url: str, timeout: int = 默认请求超时秒数) -> str:
    """下载文本内容，失败时输出中文错误。"""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise 股票池下载错误(f"下载 Nasdaq Trader 股票清单失败：{url}，原因：{exc}") from exc

    if not response.text.strip():
        raise 股票池下载错误(f"下载 Nasdaq Trader 股票清单失败：{url}，原因：返回内容为空。")

    return response.text


def 缓存原始文件(raw_dir: Path, 文件名: str, 内容: str) -> Path:
    """把原始 symbol directory 文件缓存到 data/raw。"""
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / 文件名
    path.write_text(内容, encoding="utf-8")
    return path


def 下载并缓存原始文件(
    raw_dir: Path,
    timeout: int = 默认请求超时秒数,
) -> dict[str, Path]:
    """下载 Nasdaq-listed 和 other-listed 清单，并缓存原始文件。"""
    文件配置 = {
        "nasdaqlisted": ("nasdaqlisted.txt", NASDAQ_LISTED_URL),
        "otherlisted": ("otherlisted.txt", OTHER_LISTED_URL),
    }
    raw_paths: dict[str, Path] = {}

    for key, (文件名, url) in 文件配置.items():
        内容 = 下载文本(url, timeout=timeout)
        raw_paths[key] = 缓存原始文件(raw_dir, 文件名, 内容)

    return raw_paths


def 读取_symbol_directory文本(内容: str) -> pd.DataFrame:
    """读取 Nasdaq Trader 管道分隔文本，并跳过文件生成时间行。"""
    有效行 = [
        line
        for line in 内容.splitlines()
        if line.strip() and not line.startswith("File Creation Time")
    ]
    if not 有效行:
        raise ValueError("解析股票清单失败：文件内容为空。")
    return pd.read_csv(StringIO("\n".join(有效行)), sep="|", dtype=str).fillna("")


def 是肯定值(value: str) -> bool:
    """判断 Nasdaq Trader 的 Y/N 字段是否为是。"""
    return str(value).strip().upper() == "Y"


def 布尔转中文(value: bool) -> str:
    """把布尔值转换为中文。"""
    return "是" if value else "否"


def 名称疑似非普通标的(name: str) -> bool:
    """识别 warrant、right、unit 等明显非普通股票标的。"""
    normalized = f" {name.lower()} "
    return any(
        re.search(rf"\b{re.escape(keyword)}\b", normalized)
        for keyword in 非普通标的关键词
    )


def 标准化代码(code: str) -> str:
    """标准化交易代码。"""
    return str(code).strip().upper()


def 解析纳斯达克上市清单(内容: str, 更新时间: str | None = None) -> pd.DataFrame:
    """解析 nasdaqlisted.txt 为中文字段 DataFrame。"""
    df = 读取_symbol_directory文本(内容)
    更新时间 = 更新时间 or 当前更新时间()
    rows = []

    for _, row in df.iterrows():
        市场分类 = str(row.get("Market Category", "")).strip().upper()
        rows.append(
            {
                "代码": 标准化代码(row.get("Symbol", "")),
                "名称": str(row.get("Security Name", "")).strip(),
                "市场": 纳斯达克市场映射.get(市场分类, "NASDAQ"),
                "是否ETF": 布尔转中文(是肯定值(row.get("ETF", ""))),
                "是否测试证券": 布尔转中文(是肯定值(row.get("Test Issue", ""))),
                "数据来源": "Nasdaq Trader nasdaqlisted.txt",
                "更新时间": 更新时间,
            }
        )

    return pd.DataFrame(rows, columns=股票池字段)


def 解析其他上市清单(内容: str, 更新时间: str | None = None) -> pd.DataFrame:
    """解析 otherlisted.txt 为中文字段 DataFrame。"""
    df = 读取_symbol_directory文本(内容)
    更新时间 = 更新时间 or 当前更新时间()
    rows = []

    for _, row in df.iterrows():
        交易所代码 = str(row.get("Exchange", "")).strip().upper()
        rows.append(
            {
                "代码": 标准化代码(row.get("ACT Symbol", "")),
                "名称": str(row.get("Security Name", "")).strip(),
                "市场": 其他市场映射.get(交易所代码, 交易所代码 or "其他市场"),
                "是否ETF": 布尔转中文(是肯定值(row.get("ETF", ""))),
                "是否测试证券": 布尔转中文(是肯定值(row.get("Test Issue", ""))),
                "数据来源": "Nasdaq Trader otherlisted.txt",
                "更新时间": 更新时间,
            }
        )

    return pd.DataFrame(rows, columns=股票池字段)


def 过滤股票池(df: pd.DataFrame) -> pd.DataFrame:
    """过滤测试证券和明显非普通股票 / ETF 标的。"""
    if df.empty:
        return pd.DataFrame(columns=股票池字段)

    filtered = df.copy()
    filtered["代码"] = filtered["代码"].map(标准化代码)
    filtered["名称"] = filtered["名称"].astype(str).str.strip()
    filtered = filtered[filtered["代码"] != ""]
    filtered = filtered[filtered["是否测试证券"] != "是"]

    非ETF = filtered["是否ETF"] != "是"
    非普通 = filtered["名称"].map(名称疑似非普通标的)
    filtered = filtered[~(非ETF & 非普通)]

    filtered = filtered.drop_duplicates(subset=["代码"], keep="first")
    filtered = filtered.sort_values("代码").reset_index(drop=True)

    return filtered[股票池字段]


def 合并并过滤股票池(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """合并多个清单并执行统一过滤。"""
    combined = pd.concat(list(frames), ignore_index=True)
    return 过滤股票池(combined)


def 从原始文件构建股票池(raw_paths: dict[str, Path], 更新时间: str | None = None) -> pd.DataFrame:
    """从本地原始文件构建股票池。"""
    更新时间 = 更新时间 or 当前更新时间()
    nasdaq_text = raw_paths["nasdaqlisted"].read_text(encoding="utf-8")
    other_text = raw_paths["otherlisted"].read_text(encoding="utf-8")
    nasdaq_df = 解析纳斯达克上市清单(nasdaq_text, 更新时间=更新时间)
    other_df = 解析其他上市清单(other_text, 更新时间=更新时间)
    return 合并并过滤股票池([nasdaq_df, other_df])


def 保存股票池(df: pd.DataFrame, output_path: Path) -> Path:
    """保存处理后的股票池 CSV。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def 更新股票池(
    raw_dir: Path | str = Path("data/raw"),
    output_path: Path | str = Path("data/processed/美股股票池.csv"),
    timeout: int = 默认请求超时秒数,
) -> 股票池结果:
    """下载、缓存、过滤并保存美股 / ETF 股票池。"""
    raw_dir = Path(raw_dir)
    output_path = Path(output_path)
    更新时间 = 当前更新时间()
    raw_paths = 下载并缓存原始文件(raw_dir, timeout=timeout)
    df = 从原始文件构建股票池(raw_paths, 更新时间=更新时间)
    保存股票池(df, output_path)
    return 股票池结果(数据=df, 输出路径=output_path, 原始文件路径=raw_paths)
