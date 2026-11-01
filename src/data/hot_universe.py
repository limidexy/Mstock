"""网上热度池合并与报告。

网上热度池只决定优先覆盖下载范围，不参与主升浪评分加分。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pandas as pd

from src.data.web_hot_sources import (
    HotSourceConfig,
    HotSourceProvider,
    创建热度来源,
    当前时间,
    标准化代码,
    网上热度来源字段,
    网上热度来源失败字段,
)


网上热度池字段 = [
    "代码",
    "名称",
    "来源网站",
    "来源页面",
    "来源分类",
    "入选原因",
    "热度说明",
    "最新价格",
    "当日涨幅",
    "成交量",
    "成交额",
    "市值",
    "是否ETF",
    "是否杠杆ETF",
    "是否涨幅榜",
    "是否成交量榜",
    "是否成交额榜",
    "是否热门趋势",
    "是否阶段新高",
    "更新时间",
]

杠杆ETF关键词 = [
    "2X",
    "3X",
    "2倍",
    "3倍",
    "LEVERAGED",
    "ULTRA",
    "BULL",
    "BEAR",
    "DAILY TARGET",
    "DIREXION",
    "PROSHARES ULTRA",
    "FNGU",
    "FNGD",
    "SOXL",
    "SOXS",
    "TQQQ",
    "SQQQ",
    "TECL",
    "TECS",
    "LABU",
    "LABD",
]


@dataclass(frozen=True)
class 热度池来源统计:
    """单个来源运行统计。"""

    来源键: str
    来源网站: str
    来源分类: str
    成功: bool
    数量: int
    失败原因: str = ""


@dataclass(frozen=True)
class 网上热度池结果:
    """网上热度池生成结果。"""

    数据: pd.DataFrame
    失败清单: pd.DataFrame
    来源统计: list[热度池来源统计]
    去重前数量: int
    去重后数量: int
    输出路径: Path
    报告路径: Path
    失败清单路径: Path
    是否使用网络: bool
    是否使用缓存: bool

    @property
    def 来源成功数量(self) -> int:
        """成功来源数量。"""
        return sum(1 for item in self.来源统计 if item.成功)

    @property
    def 来源失败数量(self) -> int:
        """失败来源数量。"""
        return sum(1 for item in self.来源统计 if not item.成功)


def 生成网上热度池(
    source_keys: list[str],
    output_path: Path | str,
    report_path: Path | str,
    failure_path: Path | str,
    stock_pool_path: Path | str | None = None,
    cache_dir: Path | str = Path("data/cache/daily"),
    limit: int = 500,
    config: HotSourceConfig | None = None,
    no_network: bool = False,
    logger=None,
) -> 网上热度池结果:
    """运行多个热度来源并生成合并后的热度池。"""
    if limit <= 0:
        raise ValueError("参数错误：--limit 必须大于0。")
    config = config or HotSourceConfig(no_network=no_network)
    if no_network:
        config = HotSourceConfig(
            timeout=config.timeout,
            sleep_min=config.sleep_min,
            sleep_max=config.sleep_max,
            max_retries=config.max_retries,
            use_cache=config.use_cache,
            no_network=True,
            raw_cache_dir=config.raw_cache_dir,
            session=config.session,
        )

    providers = 创建热度来源(source_keys, config=config, cache_dir=cache_dir)
    if no_network:
        providers = [provider for provider in providers if not provider.requires_network]
    frames: list[pd.DataFrame] = []
    failures: list[dict[str, str]] = []
    stats: list[热度池来源统计] = []
    now = 当前时间()

    for provider in providers:
        if logger:
            logger.info(f"正在获取网上热度来源：{provider.来源网站} / {provider.来源分类}")
        try:
            df = provider.fetch()
            df = 标准化来源表(df)
            frames.append(df)
            stats.append(热度池来源统计(provider.source_key, provider.来源网站, provider.来源分类, True, len(df)))
            if logger:
                logger.info(f"来源获取成功：{provider.来源网站} / {provider.来源分类}，数量：{len(df)}")
        except Exception as exc:  # noqa: BLE001 - 来源失败需要记录并继续
            reason = str(exc)
            failures.append(
                {
                    "来源键": provider.source_key,
                    "来源网站": provider.来源网站,
                    "来源分类": provider.来源分类,
                    "失败原因": reason,
                    "更新时间": now,
                }
            )
            stats.append(热度池来源统计(provider.source_key, provider.来源网站, provider.来源分类, False, 0, reason))
            if logger:
                logger.warning(f"来源获取失败，已记录：{provider.来源网站} / {provider.来源分类}；原因：{reason}")

    usable_frames = []
    for frame in frames:
        if frame.empty:
            continue
        normalized = frame[网上热度来源字段].copy()
        normalized = normalized.where(pd.notna(normalized), "")
        usable_frames.append(normalized)
    merged_raw = pd.concat(usable_frames, ignore_index=True) if usable_frames else pd.DataFrame(columns=网上热度来源字段)
    去重前数量 = len(merged_raw)
    metadata = 读取股票池元数据(stock_pool_path) if stock_pool_path else pd.DataFrame()
    pool = 合并网上热度池(merged_raw, metadata=metadata, limit=limit)
    去重后数量 = len(pool)

    output_path = Path(output_path)
    report_path = Path(report_path)
    failure_path = Path(failure_path)
    保存网上热度池(pool, output_path)
    failure_df = pd.DataFrame(failures, columns=网上热度来源失败字段)
    保存网上热度来源失败清单(failure_df, failure_path)

    result = 网上热度池结果(
        数据=pool,
        失败清单=failure_df,
        来源统计=stats,
        去重前数量=去重前数量,
        去重后数量=去重后数量,
        输出路径=output_path,
        报告路径=report_path,
        失败清单路径=failure_path,
        是否使用网络=not no_network,
        是否使用缓存=any(not provider.requires_network for provider in providers),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(生成网上热度池报告(result), encoding="utf-8")
    return result


def 标准化来源表(df: pd.DataFrame) -> pd.DataFrame:
    """校验并标准化单个 provider 输出。"""
    output = df.copy()
    for column in 网上热度来源字段:
        if column not in output.columns:
            output[column] = pd.NA if column in {"最新价格", "当日涨幅", "成交量", "成交额", "市值"} else ""
    output = output[网上热度来源字段].copy()
    output["代码"] = output["代码"].map(标准化代码)
    output = output[output["代码"] != ""].copy()
    output = output.drop_duplicates(subset=["代码", "来源网站", "来源分类"], keep="first").reset_index(drop=True)
    return output


def 合并网上热度池(df: pd.DataFrame, metadata: pd.DataFrame | None = None, limit: int = 500) -> pd.DataFrame:
    """按代码合并多个来源的热度记录。"""
    if df.empty:
        return pd.DataFrame(columns=网上热度池字段)

    metadata = metadata if metadata is not None else pd.DataFrame()
    metadata_by_code = {}
    if not metadata.empty and "代码" in metadata.columns:
        metadata = metadata.copy()
        metadata["代码"] = metadata["代码"].astype(str).str.upper()
        metadata_by_code = {str(row["代码"]): row for _, row in metadata.drop_duplicates("代码").iterrows()}

    rows: list[dict[str, Any]] = []
    for code, group in df.groupby("代码", sort=False):
        meta = metadata_by_code.get(code)
        name = _first_text(group["名称"].tolist())
        if not name and meta is not None:
            name = str(meta.get("名称", ""))
        is_etf = str(meta.get("是否ETF", "不足数据")) if meta is not None else "不足数据"
        leveraged = 判断是否杠杆ETF(code, name, is_etf)
        source_categories = _join_unique(group["来源分类"])
        source_sites = _join_unique(group["来源网站"])
        source_pages = _join_unique(group["来源页面"])
        reasons = _join_unique(group["入选原因"])
        heat_text = _join_unique(group["热度说明"])
        row = {
            "代码": code,
            "名称": name or "不足数据",
            "来源网站": source_sites,
            "来源页面": source_pages,
            "来源分类": source_categories,
            "入选原因": reasons,
            "热度说明": heat_text,
            "最新价格": _first_number(group["最新价格"]),
            "当日涨幅": _first_number(group["当日涨幅"]),
            "成交量": _max_number(group["成交量"]),
            "成交额": _max_number(group["成交额"]),
            "市值": _first_number(group["市值"]),
            "是否ETF": is_etf,
            "是否杠杆ETF": leveraged,
            "是否涨幅榜": _has_category(source_categories, "涨幅榜"),
            "是否成交量榜": _has_category(source_categories, "成交量榜"),
            "是否成交额榜": _has_category(source_categories, "成交额榜"),
            "是否热门趋势": _has_category(source_categories, "热门趋势"),
            "是否阶段新高": _has_category(source_categories, "阶段新高"),
            "更新时间": _first_text(group["更新时间"].tolist()) or 当前时间(),
            "_来源数量": len(set(group["来源网站"].astype(str) + "/" + group["来源分类"].astype(str))),
        }
        rows.append(row)

    output = pd.DataFrame(rows)
    output = output.sort_values(
        by=["_来源数量", "是否热门趋势", "是否涨幅榜", "是否成交量榜", "是否阶段新高", "代码"],
        ascending=[False, False, False, False, False, True],
    )
    output = output.head(limit).drop(columns=["_来源数量"]).reset_index(drop=True)
    for column in 网上热度池字段:
        if column not in output.columns:
            output[column] = ""
    return output[网上热度池字段]


def 读取股票池元数据(path: Path | str | None) -> pd.DataFrame:
    """读取股票池元数据，用于补齐名称、ETF和杠杆ETF标记。"""
    if not path:
        return pd.DataFrame()
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()
    for column in ["代码", "名称", "是否ETF"]:
        if column not in df.columns:
            df[column] = "不足数据"
    df["代码"] = df["代码"].astype(str).str.upper()
    return df[["代码", "名称", "是否ETF"]].drop_duplicates("代码", keep="first")


def 判断是否杠杆ETF(code: str, name: str, is_etf: str) -> str:
    """根据代码和名称粗略识别杠杆 ETF。"""
    text = f"{code} {name}".upper()
    if str(is_etf).strip() == "否":
        return "否"
    return "是" if any(keyword in text for keyword in 杠杆ETF关键词) else "否"


def 保存网上热度池(df: pd.DataFrame, output_path: Path | str) -> Path:
    """保存网上热度池 CSV。"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def 保存网上热度来源失败清单(df: pd.DataFrame, output_path: Path | str) -> Path:
    """保存来源失败清单，即使没有失败也写出表头。"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if df.empty:
        df = pd.DataFrame(columns=网上热度来源失败字段)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def 生成网上热度池报告(result: 网上热度池结果) -> str:
    """生成网上热度池中文报告。"""
    source_counts = result.数据["来源分类"].str.split("；").explode().value_counts().to_dict() if not result.数据.empty else {}
    top_source_contribution = _top_source_contribution(result.数据)
    recommend_download = "是" if len(result.数据) > 0 else "否"
    lines = [
        "# 网上热度池生成报告",
        "",
        f"1. 生成时间：{当前时间()}",
        f"2. 输出路径：`{result.输出路径}`",
        f"3. 来源列表：{'、'.join(item.来源键 for item in result.来源统计) if result.来源统计 else '无'}",
        f"4. 各来源成功数量：{result.来源成功数量}",
        f"5. 各来源失败数量：{result.来源失败数量}",
        f"6. 去重前数量：{result.去重前数量}",
        f"7. 去重后数量：{result.去重后数量}",
        f"8. 最终输出数量：{len(result.数据)}",
        "9. 各来源贡献数量：",
    ]
    if result.来源统计:
        for item in result.来源统计:
            status = "成功" if item.成功 else "失败"
            lines.append(f"    - {item.来源键} / {item.来源网站} / {item.来源分类}：{status}，数量 {item.数量}")
    else:
        lines.append("    - 无")
    lines.append("10. Top 来源贡献：")
    if top_source_contribution:
        for source, count in top_source_contribution.items():
            lines.append(f"    - {source}：{count}")
    else:
        lines.append("    - 无")
    lines.append("11. 来源分类数量：")
    if source_counts:
        for category, count in source_counts.items():
            lines.append(f"    - {category}：{count}")
    else:
        lines.append("    - 无")
    lines.extend(
        [
            "12. 失败来源清单：",
        ]
    )
    if result.失败清单.empty:
        lines.append("    - 无")
    else:
        for _, row in result.失败清单.iterrows():
            lines.append(f"    - {row.get('来源键', '')}：{row.get('失败原因', '')}")
    lines.extend(
        [
            f"13. 是否使用网络：{'是' if result.是否使用网络 else '否'}",
            f"14. 是否使用缓存：{'是' if result.是否使用缓存 else '否'}",
            f"15. 是否建议继续下载行情：{recommend_download}",
            "",
            "## 重要说明",
            "",
            "- 热度来源不是买入理由。",
            "- 涨幅榜不是买入理由。",
            "- 成交量榜不是买入理由。",
            "- 它们只用于让系统优先覆盖市场活跃票。",
            "- 最终判断仍看主升浪评分和人工校对。",
            "- 本系统不自动交易，不给确定性买卖建议。",
        ]
    )
    return "\n".join(lines) + "\n"


def _join_unique(values: pd.Series) -> str:
    items = []
    seen = set()
    for value in values.dropna().astype(str):
        for part in re.split(r"[；;]", value):
            part = part.strip()
            if part and part not in seen:
                seen.add(part)
                items.append(part)
    return "；".join(items)


def _first_text(values: list[Any] | pd.Series) -> str:
    for value in values:
        if pd.notna(value) and str(value).strip():
            return str(value).strip()
    return ""


def _first_number(values: pd.Series) -> Any:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.iloc[0]) if not numeric.empty else pd.NA


def _max_number(values: pd.Series) -> Any:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.max()) if not numeric.empty else pd.NA


def _has_category(text: str, keyword: str) -> str:
    return "是" if keyword in str(text) else "否"


def _top_source_contribution(df: pd.DataFrame) -> dict[str, int]:
    if df.empty or "来源网站" not in df.columns:
        return {}
    counts: dict[str, int] = {}
    for value in df["来源网站"].dropna().astype(str):
        for part in value.split("；"):
            part = part.strip()
            if part:
                counts[part] = counts.get(part, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10])
