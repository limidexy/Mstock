"""下载候选池构建。

本模块只负责扩大数据验证的样本覆盖，不参与评分加分，也不构成交易推荐。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

import pandas as pd

from src.data.universe import 名称疑似非普通标的


下载候选池字段 = ["代码", "名称", "市场", "是否ETF", "候选池来源", "入选原因", "股票池匹配"]
最大自动候选池规模 = 500

验证种子代码 = [
    "QQQ",
    "SPY",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMD",
    "AVGO",
    "TSM",
    "ARM",
    "MU",
    "SMCI",
    "ASML",
    "LRCX",
    "AMAT",
    "KLAC",
    "QCOM",
    "INTC",
    "PLTR",
    "CRWD",
    "PANW",
    "NET",
    "SNOW",
    "DDOG",
    "MDB",
    "SHOP",
    "MELI",
    "SE",
    "TSLA",
    "META",
    "GOOGL",
    "AMZN",
    "NFLX",
    "COIN",
    "MSTR",
    "HOOD",
    "APP",
    "TTD",
    "UBER",
    "ABNB",
    "RBLX",
    "SQ",
    "PYPL",
    "SOFI",
    "DKNG",
    "ROKU",
    "BABA",
    "PDD",
    "NIO",
    "LI",
    "XPEV",
    "SMH",
    "SOXX",
    "IGV",
    "XLK",
    "XLY",
    "XLF",
    "XLE",
    "XLI",
    "XLC",
    "ARKK",
    "TQQQ",
    "SQQQ",
    "SOXL",
    "SOXS",
    "TECL",
    "TECS",
    "LABU",
    "LABD",
    "FNGU",
    "FNGD",
]

行业ETF代码 = {"QQQ", "SPY", "SMH", "SOXX", "IGV", "XLK", "XLY", "XLF", "XLE", "XLI", "XLC", "ARKK"}
杠杆ETF验证代码 = {"TQQQ", "SQQQ", "SOXL", "SOXS", "TECL", "TECS", "LABU", "LABD", "FNGU", "FNGD"}
基准代码 = {"QQQ", "SPY"}
明显非目标关键词 = [
    "warrant",
    "warrants",
    "right",
    "rights",
    "unit",
    "units",
    "preferred",
    "preference",
    "depositary",
    "note",
    "notes",
    "bond",
    "debenture",
]


@dataclass(frozen=True)
class 下载候选池结果:
    """下载候选池构建结果。"""

    数据: pd.DataFrame
    输出路径: Path
    目标数量: int
    股票池数量: int
    种子数量: int
    分层抽样数量: int
    未匹配种子: list[str]


def 标准化代码(code: str) -> str:
    """标准化交易代码。"""
    return str(code).strip().upper()


def 去重保序(codes: list[str]) -> list[str]:
    """保持顺序去重。"""
    seen = set()
    result = []
    for code in codes:
        normalized = 标准化代码(code)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def 读取股票池(path: Path | str) -> pd.DataFrame:
    """读取中文股票池。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"股票池文件不存在：{path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    required = ["代码", "名称", "市场", "是否ETF"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"股票池字段缺失：{'、'.join(missing)}")
    if "是否测试证券" not in df.columns:
        df["是否测试证券"] = "否"
    return df


def 是明显非目标标的(row: pd.Series) -> bool:
    """识别测试证券、权证、rights、units 等不适合纳入下载验证的标的。"""
    code = 标准化代码(row.get("代码", ""))
    if "$" in code or "^" in code:
        return True
    if str(row.get("是否测试证券", "")).strip() == "是":
        return True
    name = str(row.get("名称", ""))
    if 名称疑似非普通标的(name):
        return True
    normalized_name = f" {name.lower()} "
    return any(re.search(rf"\b{re.escape(keyword)}\b", normalized_name) for keyword in 明显非目标关键词)


def 清洗股票池(df: pd.DataFrame) -> pd.DataFrame:
    """清洗股票池，保留普通股票和 ETF。"""
    output = df.copy()
    output["代码"] = output["代码"].map(标准化代码)
    output["名称"] = output["名称"].fillna("").astype(str).str.strip()
    output = output[output["代码"] != ""]
    output = output[~output.apply(是明显非目标标的, axis=1)]
    output = output.drop_duplicates("代码", keep="first").sort_values("代码").reset_index(drop=True)
    return output


def 种子来源和原因(code: str) -> tuple[str, str]:
    """返回验证种子的来源和中文原因。"""
    if code in 基准代码:
        return "基准指数", "相对强度基准"
    if code in 行业ETF代码:
        return "行业ETF", "行业ETF覆盖"
    if code in 杠杆ETF验证代码:
        return "验证种子", "杠杆ETF高风险样本覆盖"
    return "验证种子", "提高验证覆盖"


def 构建种子行(code: str, pool_by_code: dict[str, pd.Series]) -> dict[str, str]:
    """构建单个种子代码行。"""
    source, reason = 种子来源和原因(code)
    if code in pool_by_code:
        row = pool_by_code[code]
        return {
            "代码": code,
            "名称": str(row.get("名称", "")),
            "市场": str(row.get("市场", "")),
            "是否ETF": str(row.get("是否ETF", "不足数据")),
            "候选池来源": source,
            "入选原因": reason,
            "股票池匹配": "是",
        }
    return {
        "代码": code,
        "名称": "股票池未匹配",
        "市场": "不足数据",
        "是否ETF": "不足数据",
        "候选池来源": source,
        "入选原因": f"{reason}；股票池未匹配，仍用于链路验证",
        "股票池匹配": "否",
    }


def 分层抽样补足(pool: pd.DataFrame, 已选代码: set[str], 需要数量: int) -> list[dict[str, str]]:
    """按代码首字母和 ETF/普通股票分层抽样补足候选池。"""
    if 需要数量 <= 0:
        return []
    candidates = pool[~pool["代码"].isin(已选代码)].copy()
    if candidates.empty:
        return []
    candidates["首字母"] = candidates["代码"].str[0].where(candidates["代码"].str[0].str.match(r"[A-Z]"), "#")
    letters = sorted(candidates["首字母"].dropna().unique().tolist())
    rows: list[dict[str, str]] = []
    pointers: dict[tuple[str, str], int] = {}
    grouped: dict[tuple[str, str], pd.DataFrame] = {}

    for letter in letters:
        for is_etf in ["是", "否"]:
            group = candidates[(candidates["首字母"] == letter) & (candidates["是否ETF"] == is_etf)].sort_values("代码").reset_index(drop=True)
            if not group.empty:
                key = (letter, is_etf)
                grouped[key] = group
                pointers[key] = 0

    while len(rows) < 需要数量 and grouped:
        added = False
        for letter in letters:
            for is_etf in ["是", "否"]:
                key = (letter, is_etf)
                group = grouped.get(key)
                if group is None:
                    continue
                pointer = pointers[key]
                if pointer >= len(group):
                    continue
                row = group.iloc[pointer]
                pointers[key] = pointer + 1
                rows.append(
                    {
                        "代码": str(row["代码"]),
                        "名称": str(row.get("名称", "")),
                        "市场": str(row.get("市场", "")),
                        "是否ETF": str(row.get("是否ETF", "否")),
                        "候选池来源": "分层抽样",
                        "入选原因": "股票池分散抽样",
                        "股票池匹配": "是",
                    }
                )
                已选代码.add(str(row["代码"]))
                added = True
                if len(rows) >= 需要数量:
                    break
            if len(rows) >= 需要数量:
                break
        if not added:
            break
    return rows


def 构建下载候选池(
    stock_pool_path: Path | str,
    target_size: int = 200,
    output_path: Path | str | None = None,
) -> 下载候选池结果:
    """构建更有代表性的下载候选池。"""
    if target_size <= 0:
        raise ValueError("目标候选池规模必须大于0。")
    if target_size > 最大自动候选池规模:
        raise ValueError("目标候选池规模超过500，本轮不会自动构建或下载。")

    raw_pool = 读取股票池(stock_pool_path)
    pool = 清洗股票池(raw_pool)
    pool_by_code = {str(row["代码"]): row for _, row in pool.iterrows()}
    seed_codes = 去重保序(验证种子代码)
    selected_rows: list[dict[str, str]] = []
    selected_codes: set[str] = set()
    unmatched_seeds: list[str] = []

    for code in seed_codes:
        if len(selected_rows) >= target_size:
            break
        row = 构建种子行(code, pool_by_code)
        selected_rows.append(row)
        selected_codes.add(code)
        if row["股票池匹配"] == "否":
            unmatched_seeds.append(code)

    fill_rows = 分层抽样补足(pool, selected_codes, target_size - len(selected_rows))
    selected_rows.extend(fill_rows)

    output = pd.DataFrame(selected_rows, columns=下载候选池字段).drop_duplicates("代码", keep="first")
    output = output.head(target_size).reset_index(drop=True)
    if not {"QQQ", "SPY"}.issubset(set(output["代码"])):
        raise ValueError("下载候选池构建失败：缺少 QQQ 或 SPY。")

    output_path = Path(output_path) if output_path else Path("data/processed") / f"下载候选池_{target_size}.csv"
    保存下载候选池(output, output_path)
    return 下载候选池结果(
        数据=output,
        输出路径=output_path,
        目标数量=target_size,
        股票池数量=len(pool),
        种子数量=int((output["候选池来源"] != "分层抽样").sum()),
        分层抽样数量=int((output["候选池来源"] == "分层抽样").sum()),
        未匹配种子=unmatched_seeds,
    )


def 保存下载候选池(df: pd.DataFrame, output_path: Path | str) -> Path:
    """保存下载候选池 CSV。"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def 生成候选池构建报告(result: 下载候选池结果) -> str:
    """生成下载候选池构建报告。"""
    source_counts = result.数据["候选池来源"].value_counts().to_dict()
    first_letters = sorted(result.数据["代码"].astype(str).str[0].unique().tolist())
    lines = [
        "# 下载候选池构建报告",
        "",
        f"1. 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"2. 目标候选池规模：{result.目标数量}",
        f"3. 实际候选池数量：{len(result.数据)}",
        f"4. 输出路径：`{result.输出路径}`",
        f"5. 清洗后股票池数量：{result.股票池数量}",
        f"6. 验证种子数量：{result.种子数量}",
        f"7. 分层抽样数量：{result.分层抽样数量}",
        f"8. 是否包含 QQQ：{'是' if 'QQQ' in set(result.数据['代码']) else '否'}",
        f"9. 是否包含 SPY：{'是' if 'SPY' in set(result.数据['代码']) else '否'}",
        f"10. 覆盖首字母数量：{len(first_letters)}",
        "11. 候选池来源分布：",
    ]
    for source, count in source_counts.items():
        lines.append(f"    - {source}：{count}")
    lines.extend(
        [
            "12. 未匹配股票池的种子代码：",
            f"    - {'、'.join(result.未匹配种子) if result.未匹配种子 else '无'}",
            "",
            "## 重要说明",
            "",
            "- 验证种子列表只用于扩大样本覆盖，不是最终候选结果，不是交易推荐。",
            "- 系统最终候选仍由技术特征和评分规则决定，种子代码不会获得任何评分加分。",
            "- 分层抽样用于避免只下载字母表前排股票。",
        ]
    )
    return "\n".join(lines) + "\n"
