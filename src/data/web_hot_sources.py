"""网上热度来源。

本模块只负责发现“值得优先覆盖下载”的美股 / ETF 代码，不参与评分加分。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import hashlib
from io import StringIO
from pathlib import Path
import json
import random
import re
import time
from typing import Any

import pandas as pd
import requests


网上热度来源字段 = [
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
    "更新时间",
]

网上热度来源失败字段 = ["来源键", "来源网站", "来源分类", "失败原因", "更新时间"]

默认请求头 = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
}

无效代码关键词 = {"", "NAN", "NONE", "NULL", "N/A", "SYMBOL"}
允许美股类别后缀 = {"A", "B", "C"}
东方财富美股榜页面 = "https://quote.eastmoney.com/center/gridlist.html#us_stocks"
东方财富美股榜接口 = "https://push2.eastmoney.com/api/qt/clist/get"


class 网上热度来源错误(RuntimeError):
    """网上热度来源抓取失败。"""


@dataclass(frozen=True)
class HotSourceConfig:
    """网上热度请求配置。"""

    timeout: int = 15
    sleep_min: float = 1.0
    sleep_max: float = 3.0
    max_retries: int = 2
    use_cache: bool = True
    no_network: bool = False
    raw_cache_dir: Path = Path("data/raw/hot_sources")
    session: Any | None = None


class HotSourceProvider(ABC):
    """网上热度来源抽象接口。"""

    source_key = "base"
    来源网站 = "未知来源"
    来源页面 = ""
    来源分类 = "未知分类"
    入选原因 = "网上热度来源"
    requires_network = True

    def __init__(self, config: HotSourceConfig | None = None, cache_dir: Path | str = Path("data/cache/daily")) -> None:
        self.config = config or HotSourceConfig()
        self.cache_dir = Path(cache_dir)
        self.session = self.config.session or requests.Session()

    @abstractmethod
    def fetch(self) -> pd.DataFrame:
        """获取统一字段的网上热度数据。"""

    def _request_text(self, url: str, method: str = "GET", json_payload: dict[str, Any] | None = None) -> str:
        """请求网页文本，带超时、重试、请求间隔和原始响应缓存。"""
        if self.config.no_network:
            raise 网上热度来源错误(f"{self.来源网站} 已启用 --no-network，跳过联网来源。")

        attempts = self.config.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                self._sleep(attempt)
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=默认请求头,
                    timeout=self.config.timeout,
                    json=json_payload,
                )
                if response.status_code >= 400:
                    raise 网上热度来源错误(f"HTTP {response.status_code}：{response.text[:160]}")
                text = response.text
                if self.config.use_cache:
                    self._cache_raw_response(text, cache_key=self._cache_key(method, url, json_payload))
                return text
            except Exception as exc:  # noqa: BLE001 - 需要保留原始失败原因
                last_error = exc
        if self.config.use_cache:
            cached = self._load_cached_response(cache_key=self._cache_key(method, url, json_payload))
            if cached:
                return cached
        raise 网上热度来源错误(f"{self.来源网站} 请求失败：{last_error}")

    def _request_json(self, url: str, method: str = "GET", json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """请求并解析 JSON。"""
        text = self._request_text(url, method=method, json_payload=json_payload)
        try:
            return json.loads(text)
        except Exception as exc:  # noqa: BLE001
            raise 网上热度来源错误(f"{self.来源网站} JSON 解析失败：{exc}") from exc

    def _sleep(self, attempt: int) -> None:
        """请求间隔和重试退避。"""
        lower = max(0.0, self.config.sleep_min)
        upper = max(lower, self.config.sleep_max)
        if upper <= 0:
            return
        seconds = random.uniform(lower, upper) * (2 ** max(0, attempt - 2))
        time.sleep(seconds)

    def _cache_raw_response(self, text: str, cache_key: str | None = None) -> None:
        """缓存单个来源的原始响应。"""
        try:
            self.config.raw_cache_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y%m%d")
            safe_key = re.sub(r"[^A-Za-z0-9_\-]+", "_", self.source_key)
            suffix = f"_{cache_key}" if cache_key else ""
            path = self.config.raw_cache_dir / f"{safe_key}_{today}{suffix}.txt"
            path.write_text(text, encoding="utf-8")
        except Exception:
            return

    def _load_cached_response(self, cache_key: str) -> str:
        """请求失败时读取同日原始响应缓存。"""
        try:
            today = datetime.now().strftime("%Y%m%d")
            safe_key = re.sub(r"[^A-Za-z0-9_\-]+", "_", self.source_key)
            exact_path = self.config.raw_cache_dir / f"{safe_key}_{today}_{cache_key}.txt"
            if exact_path.exists():
                return exact_path.read_text(encoding="utf-8")
            legacy_path = self.config.raw_cache_dir / f"{safe_key}_{today}.txt"
            if legacy_path.exists():
                return legacy_path.read_text(encoding="utf-8")
        except Exception:
            return ""
        return ""

    def _cache_key(self, method: str, url: str, json_payload: dict[str, Any] | None = None) -> str:
        """为同一来源的不同页面生成缓存键。"""
        raw = f"{method}|{url}|{json.dumps(json_payload, sort_keys=True, ensure_ascii=False) if json_payload else ''}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def _finalize(self, rows: list[dict[str, Any]]) -> pd.DataFrame:
        """补齐统一字段并清洗代码。"""
        now = 当前时间()
        output_rows: list[dict[str, Any]] = []
        for row in rows:
            ticker = 标准化代码(row.get("代码", ""))
            if not ticker:
                continue
            normalized = {column: row.get(column, "") for column in 网上热度来源字段}
            normalized["代码"] = ticker
            normalized["来源网站"] = normalized.get("来源网站") or self.来源网站
            normalized["来源页面"] = normalized.get("来源页面") or self.来源页面
            normalized["来源分类"] = normalized.get("来源分类") or self.来源分类
            normalized["入选原因"] = normalized.get("入选原因") or self.入选原因
            normalized["热度说明"] = normalized.get("热度说明") or self.来源分类
            normalized["更新时间"] = normalized.get("更新时间") or now
            output_rows.append(normalized)
        return pd.DataFrame(output_rows, columns=网上热度来源字段)


class YahooTrendingProvider(HotSourceProvider):
    """Yahoo Finance 热门趋势。"""

    source_key = "yahoo_trending"
    来源网站 = "Yahoo Finance"
    来源页面 = "https://finance.yahoo.com/markets/stocks/trending/"
    来源分类 = "热门趋势"
    入选原因 = "Yahoo Finance 热门趋势"

    def fetch(self) -> pd.DataFrame:
        payload = self._request_json("https://query1.finance.yahoo.com/v1/finance/trending/US?count=100")
        quotes = payload.get("finance", {}).get("result", [{}])[0].get("quotes", [])
        rows = []
        for quote in quotes:
            rows.append(_yahoo_quote_to_row(quote, self))
        if not rows:
            raise 网上热度来源错误("Yahoo 热门趋势没有解析到股票代码。")
        return self._finalize(rows)


class YahooGainersProvider(HotSourceProvider):
    """Yahoo Finance 涨幅榜。"""

    source_key = "yahoo_gainers"
    来源网站 = "Yahoo Finance"
    来源页面 = "https://finance.yahoo.com/markets/stocks/gainers/"
    来源分类 = "涨幅榜"
    入选原因 = "Yahoo Finance 涨幅榜"
    screener_id = "day_gainers"

    def fetch(self) -> pd.DataFrame:
        return _fetch_yahoo_screener(self, self.screener_id, count=100)


class YahooMostActiveProvider(HotSourceProvider):
    """Yahoo Finance 成交活跃榜。"""

    source_key = "yahoo_active"
    来源网站 = "Yahoo Finance"
    来源页面 = "https://finance.yahoo.com/markets/stocks/most-active/"
    来源分类 = "成交量榜"
    入选原因 = "Yahoo Finance 成交活跃榜"
    screener_id = "most_actives"

    def fetch(self) -> pd.DataFrame:
        return _fetch_yahoo_screener(self, self.screener_id, count=100)


class NasdaqMostActiveProvider(HotSourceProvider):
    """Nasdaq 成交活跃榜。"""

    source_key = "nasdaq_active"
    来源网站 = "Nasdaq"
    来源页面 = "https://www.nasdaq.com/market-activity/stocks/most-active"
    来源分类 = "成交量榜"
    入选原因 = "Nasdaq 成交活跃榜"

    def fetch(self) -> pd.DataFrame:
        url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=300&offset=0&download=true"
        payload = self._request_json(url)
        rows_data = payload.get("data", {}).get("rows", [])
        if not rows_data:
            raise 网上热度来源错误("Nasdaq 没有返回可解析的股票列表。")
        parsed_rows = []
        for item in rows_data:
            price = 解析数字(item.get("lastsale"))
            volume = 解析数字(item.get("volume"))
            parsed_rows.append(
                {
                    "代码": item.get("symbol"),
                    "名称": item.get("name", ""),
                    "最新价格": price,
                    "当日涨幅": 解析百分比(item.get("pctchange")),
                    "成交量": volume,
                    "成交额": price * volume if pd.notna(price) and pd.notna(volume) else pd.NA,
                    "市值": 解析数字(item.get("marketCap")),
                    "热度说明": "Nasdaq 公开股票列表按成交量筛选",
                }
            )
        parsed_rows = sorted(parsed_rows, key=lambda row: _sort_number(row.get("成交量")), reverse=True)[:100]
        return self._finalize(parsed_rows)


class StockAnalysisGainersProvider(HotSourceProvider):
    """StockAnalysis 涨幅榜。"""

    source_key = "stockanalysis_gainers"
    来源网站 = "StockAnalysis"
    来源页面 = "https://stockanalysis.com/markets/gainers/"
    来源分类 = "涨幅榜"
    入选原因 = "StockAnalysis 涨幅榜"

    def fetch(self) -> pd.DataFrame:
        return _fetch_stockanalysis_table(self)


class StockAnalysisMostActiveProvider(HotSourceProvider):
    """StockAnalysis 成交活跃榜。"""

    source_key = "stockanalysis_active"
    来源网站 = "StockAnalysis"
    来源页面 = "https://stockanalysis.com/markets/active/"
    来源分类 = "成交量榜"
    入选原因 = "StockAnalysis 成交活跃榜"

    def fetch(self) -> pd.DataFrame:
        return _fetch_stockanalysis_table(self)


class TradingViewGainersProvider(HotSourceProvider):
    """TradingView 美股涨幅榜。"""

    source_key = "tradingview_gainers"
    来源网站 = "TradingView"
    来源页面 = "https://www.tradingview.com/markets/stocks-usa/market-movers-gainers/"
    来源分类 = "涨幅榜"
    入选原因 = "TradingView 美股涨幅榜"

    def fetch(self) -> pd.DataFrame:
        payload = {
            "columns": ["name", "description", "close", "change", "volume", "Value.Traded", "market_cap_basic"],
            "filter": [{"left": "type", "operation": "equal", "right": "stock"}],
            "ignore_unknown_fields": False,
            "options": {"lang": "zh"},
            "range": [0, 100],
            "sort": {"sortBy": "change", "sortOrder": "desc"},
            "symbols": {},
        }
        data = self._request_json("https://scanner.tradingview.com/america/scan", method="POST", json_payload=payload)
        rows = []
        for item in data.get("data", []):
            values = item.get("d", [])
            symbol = values[0] if len(values) > 0 else item.get("s", "").split(":")[-1]
            price = values[2] if len(values) > 2 else pd.NA
            volume = values[4] if len(values) > 4 else pd.NA
            rows.append(
                {
                    "代码": symbol,
                    "名称": values[1] if len(values) > 1 else "",
                    "最新价格": 解析数字(price),
                    "当日涨幅": 解析百分比(values[3] if len(values) > 3 else pd.NA),
                    "成交量": 解析数字(volume),
                    "成交额": 解析数字(values[5] if len(values) > 5 else pd.NA),
                    "市值": 解析数字(values[6] if len(values) > 6 else pd.NA),
                    "热度说明": "TradingView 美股涨幅榜",
                }
            )
        if not rows:
            raise 网上热度来源错误("TradingView 没有解析到股票代码。")
        return self._finalize(rows)


class CachedBreakoutProvider(HotSourceProvider):
    """从本地缓存计算阶段新高。"""

    source_key = "cached_breakout"
    来源网站 = "本地缓存"
    来源页面 = "data/cache/daily/"
    来源分类 = "阶段新高"
    入选原因 = "本地缓存计算阶段新高"
    requires_network = False

    def fetch(self) -> pd.DataFrame:
        rows = []
        for path in sorted(self.cache_dir.glob("*.csv")):
            try:
                df = pd.read_csv(path, encoding="utf-8-sig").sort_values("日期").reset_index(drop=True)
                row = _cached_breakout_row(df, path.stem.upper(), self)
                if row:
                    rows.append(row)
            except Exception:
                continue
        return self._finalize(rows)


class CachedVolumeSurgeProvider(HotSourceProvider):
    """从本地缓存计算异常放量。"""

    source_key = "cached_volume"
    来源网站 = "本地缓存"
    来源页面 = "data/cache/daily/"
    来源分类 = "异常放量"
    入选原因 = "本地缓存计算异常放量"
    requires_network = False

    def fetch(self) -> pd.DataFrame:
        rows = []
        for path in sorted(self.cache_dir.glob("*.csv")):
            try:
                df = pd.read_csv(path, encoding="utf-8-sig").sort_values("日期").reset_index(drop=True)
                row = _cached_volume_row(df, path.stem.upper(), self)
                if row:
                    rows.append(row)
            except Exception:
                continue
        return self._finalize(rows)


class EastMoneyHotProvider(HotSourceProvider):
    """东方财富公开美股榜。"""

    source_key = "eastmoney_hot"
    来源网站 = "东方财富"
    来源页面 = 东方财富美股榜页面
    来源分类 = "国内公开热度"
    入选原因 = "东方财富公开美股榜"

    def fetch(self) -> pd.DataFrame:
        configs = [
            ("f3", "涨幅榜", "东方财富美股涨幅榜"),
            ("f5", "成交量榜", "东方财富美股成交量榜"),
            ("f6", "成交额榜", "东方财富美股成交额榜"),
        ]
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for sort_field, category, reason in configs:
            url = (
                f"{东方财富美股榜接口}?pn=1&pz=100&po=1&np=1"
                "&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2"
                f"&fid={sort_field}&fs=m:105,m:106,m:107&fields=f12,f14,f2,f3,f5,f6,f20"
            )
            try:
                payload = self._request_json(url)
            except Exception as exc:  # noqa: BLE001 - 单个分榜失败不能拖掉整个国内源
                errors.append(f"{category}失败：{exc}")
                continue
            diff = payload.get("data", {}).get("diff", [])
            for item in diff:
                rows.append(
                    {
                        "代码": item.get("f12"),
                        "名称": item.get("f14", ""),
                        "来源网站": self.来源网站,
                        "来源页面": self.来源页面,
                        "来源分类": category,
                        "入选原因": reason,
                        "热度说明": reason,
                        "最新价格": 解析数字(item.get("f2")),
                        "当日涨幅": 解析百分比(item.get("f3")),
                        "成交量": 解析数字(item.get("f5")),
                        "成交额": 解析数字(item.get("f6")),
                        "市值": 解析数字(item.get("f20")),
                    }
                )
        output = self._finalize(rows)
        if output.empty:
            error_text = "；".join(errors) if errors else "没有返回可解析数据"
            raise 网上热度来源错误(f"东方财富公开美股榜没有解析到股票代码：{error_text}")
        return output


class XueqiuHotProvider(HotSourceProvider):
    """雪球热度占位来源。"""

    source_key = "xueqiu_hot"
    来源网站 = "雪球"
    来源页面 = "暂未启用"
    来源分类 = "国内社区热度"
    入选原因 = "雪球热度占位"

    def fetch(self) -> pd.DataFrame:
        raise 网上热度来源错误("雪球公开接口当前要求登录，本系统不绕过登录，已优雅跳过。")


class TonghuashunHotProvider(HotSourceProvider):
    """同花顺公开美股页面。"""

    source_key = "tonghuashun_hot"
    来源网站 = "同花顺"
    来源页面 = "https://q.10jqka.com.cn/usa/"
    来源分类 = "国内公开热度"
    入选原因 = "同花顺公开美股页面"

    def fetch(self) -> pd.DataFrame:
        text = self._request_text(self.来源页面)
        if "chameleon" in text and "window.location.href" in text and "401" in text[:1000]:
            raise 网上热度来源错误("同花顺页面触发访问校验，本系统不绕过校验，已优雅跳过。")
        try:
            tables = pd.read_html(StringIO(text))
        except Exception as exc:  # noqa: BLE001
            raise 网上热度来源错误(f"同花顺页面表格解析失败：{exc}") from exc
        rows: list[dict[str, Any]] = []
        for table_index, table in enumerate(tables[:5], start=1):
            if "代码" not in table.columns:
                continue
            category = "涨幅榜" if "涨跌幅(%)" in table.columns else "国内公开热度"
            for _, row in table.iterrows():
                price = 解析数字(row.get("现价"))
                volume = 解析数字(row.get("成交量"))
                rows.append(
                    {
                        "代码": row.get("代码"),
                        "名称": row.get("名称", ""),
                        "来源网站": self.来源网站,
                        "来源页面": self.来源页面,
                        "来源分类": category,
                        "入选原因": f"同花顺公开美股表格第{table_index}组",
                        "热度说明": f"同花顺公开美股表格第{table_index}组",
                        "最新价格": price,
                        "当日涨幅": 解析百分比(row.get("涨跌幅(%)")),
                        "成交量": volume,
                        "成交额": price * volume if pd.notna(price) and pd.notna(volume) else pd.NA,
                        "市值": pd.NA,
                    }
                )
        output = self._finalize(rows)
        if output.empty:
            raise 网上热度来源错误("同花顺公开美股页面没有解析到股票代码。")
        return output


来源注册表 = {
    "yahoo_trending": YahooTrendingProvider,
    "yahoo_gainers": YahooGainersProvider,
    "yahoo_active": YahooMostActiveProvider,
    "nasdaq_active": NasdaqMostActiveProvider,
    "stockanalysis_gainers": StockAnalysisGainersProvider,
    "stockanalysis_active": StockAnalysisMostActiveProvider,
    "tradingview_gainers": TradingViewGainersProvider,
    "cached_breakout": CachedBreakoutProvider,
    "cached_volume": CachedVolumeSurgeProvider,
    "eastmoney_hot": EastMoneyHotProvider,
    "xueqiu_hot": XueqiuHotProvider,
    "tonghuashun_hot": TonghuashunHotProvider,
}

默认来源列表 = [
    "eastmoney_hot",
    "tonghuashun_hot",
    "yahoo_trending",
    "yahoo_gainers",
    "yahoo_active",
    "nasdaq_active",
    "stockanalysis_gainers",
    "stockanalysis_active",
    "tradingview_gainers",
    "cached_breakout",
    "cached_volume",
]


def 创建热度来源(source_keys: list[str], config: HotSourceConfig, cache_dir: Path | str) -> list[HotSourceProvider]:
    """按来源键创建 provider。"""
    providers: list[HotSourceProvider] = []
    unknown = [key for key in source_keys if key not in 来源注册表]
    if unknown:
        raise ValueError(f"未知网上热度来源：{'、'.join(unknown)}")
    for key in source_keys:
        providers.append(来源注册表[key](config=config, cache_dir=cache_dir))
    return providers


def 当前时间() -> str:
    """返回上海时区中文输出时间。"""
    return pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S")


def 标准化代码(value: Any) -> str:
    """标准化美股代码。"""
    text = str(value).strip().upper()
    text = text.split(":")[-1]
    text = re.sub(r"\s+", "", text)
    if text in 无效代码关键词:
        return ""
    if "." in text:
        base, suffix = text.rsplit(".", 1)
        if suffix not in 允许美股类别后缀:
            return ""
        text = f"{base}-{suffix}"
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", text):
        return ""
    return text


def 解析数字(value: Any) -> float | pd._libs.missing.NAType:
    """解析带单位、逗号、货币符号的数字。"""
    if value is None or pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if text in {"", "-", "--", "—", "N/A", "nan", "None"}:
        return pd.NA
    text = text.replace("$", "").replace(",", "").replace("%", "").strip()
    multiplier = 1.0
    if text and text[-1] in {"万", "亿"}:
        suffix = text[-1]
        text = text[:-1]
        multiplier = {"万": 10_000, "亿": 100_000_000}[suffix]
    if text and text[-1].upper() in {"K", "M", "B", "T"}:
        suffix = text[-1].upper()
        text = text[:-1]
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}[suffix]
    try:
        return float(text) * multiplier
    except ValueError:
        return pd.NA


def 解析百分比(value: Any) -> float | pd._libs.missing.NAType:
    """解析百分比，统一为小数形式。"""
    number = 解析数字(value)
    if pd.isna(number):
        return pd.NA
    return float(number) / 100 if abs(float(number)) > 1 else float(number)


def _fetch_yahoo_screener(provider: HotSourceProvider, screener_id: str, count: int = 100) -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds={screener_id}&count={count}"
    payload = provider._request_json(url)
    quotes = payload.get("finance", {}).get("result", [{}])[0].get("quotes", [])
    rows = [_yahoo_quote_to_row(quote, provider) for quote in quotes]
    if not rows:
        raise 网上热度来源错误(f"{provider.来源网站} {provider.来源分类} 没有解析到股票代码。")
    return provider._finalize(rows)


def _yahoo_quote_to_row(quote: dict[str, Any], provider: HotSourceProvider) -> dict[str, Any]:
    price = 解析数字(quote.get("regularMarketPrice"))
    volume = 解析数字(quote.get("regularMarketVolume"))
    return {
        "代码": quote.get("symbol"),
        "名称": quote.get("shortName") or quote.get("longName") or quote.get("displayName") or "",
        "来源网站": provider.来源网站,
        "来源页面": provider.来源页面,
        "来源分类": provider.来源分类,
        "入选原因": provider.入选原因,
        "热度说明": f"Yahoo Finance {provider.来源分类}",
        "最新价格": price,
        "当日涨幅": 解析百分比(quote.get("regularMarketChangePercent")),
        "成交量": volume,
        "成交额": price * volume if pd.notna(price) and pd.notna(volume) else pd.NA,
        "市值": 解析数字(quote.get("marketCap")),
    }


def _fetch_stockanalysis_table(provider: HotSourceProvider) -> pd.DataFrame:
    text = provider._request_text(provider.来源页面)
    try:
        tables = pd.read_html(StringIO(text))
    except Exception as exc:  # noqa: BLE001
        raise 网上热度来源错误(f"StockAnalysis 表格解析失败：{exc}") from exc
    if not tables:
        raise 网上热度来源错误("StockAnalysis 页面没有可解析表格。")
    table = tables[0]
    symbol_col = _find_column(table, ["Symbol", "代码"])
    name_col = _find_column(table, ["Company Name", "Name", "名称"])
    price_col = _find_column(table, ["Price", "Last Price", "最新价格"])
    change_col = _find_column(table, ["% Change", "Change %", "Chg %", "%Chg"])
    volume_col = _find_column(table, ["Volume", "成交量"])
    market_cap_col = _find_column(table, ["Market Cap", "市值"])
    rows = []
    for _, row in table.iterrows():
        price = 解析数字(row.get(price_col)) if price_col else pd.NA
        volume = 解析数字(row.get(volume_col)) if volume_col else pd.NA
        rows.append(
            {
                "代码": row.get(symbol_col) if symbol_col else "",
                "名称": row.get(name_col) if name_col else "",
                "最新价格": price,
                "当日涨幅": 解析百分比(row.get(change_col)) if change_col else pd.NA,
                "成交量": volume,
                "成交额": price * volume if pd.notna(price) and pd.notna(volume) else pd.NA,
                "市值": 解析数字(row.get(market_cap_col)) if market_cap_col else pd.NA,
                "热度说明": f"StockAnalysis {provider.来源分类}",
            }
        )
    output = provider._finalize(rows)
    if output.empty:
        raise 网上热度来源错误("StockAnalysis 没有解析到股票代码。")
    return output


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {str(column).strip().lower(): column for column in df.columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in normalized:
            return normalized[key]
    for column in df.columns:
        lower = str(column).strip().lower()
        if any(candidate.strip().lower() in lower for candidate in candidates):
            return column
    return None


def _cached_breakout_row(df: pd.DataFrame, ticker: str, provider: HotSourceProvider) -> dict[str, Any] | None:
    if len(df) < 21 or "最高价" not in df.columns or "收盘价" not in df.columns:
        return None
    output = df.copy()
    output["收盘价"] = pd.to_numeric(output["收盘价"], errors="coerce")
    output["最高价"] = pd.to_numeric(output["最高价"], errors="coerce")
    output["成交量"] = pd.to_numeric(output.get("成交量", pd.Series(dtype=float)), errors="coerce")
    latest = output.iloc[-1]
    close = latest.get("收盘价")
    if pd.isna(close):
        return None
    broken: list[str] = []
    for window in (20, 60, 120):
        if len(output) <= window:
            continue
        previous_high = output["最高价"].rolling(window=window, min_periods=window).max().shift(1).iloc[-1]
        if pd.notna(previous_high) and close >= previous_high:
            broken.append(f"{window}日新高")
    if not broken:
        return None
    return _cached_common_row(output, ticker, provider, f"突破{'、'.join(broken)}")


def _cached_volume_row(df: pd.DataFrame, ticker: str, provider: HotSourceProvider) -> dict[str, Any] | None:
    if len(df) < 20 or "成交量" not in df.columns or "收盘价" not in df.columns:
        return None
    output = df.copy()
    output["成交量"] = pd.to_numeric(output["成交量"], errors="coerce")
    output["收盘价"] = pd.to_numeric(output["收盘价"], errors="coerce")
    mavol20 = output["成交量"].rolling(window=20, min_periods=20).mean().iloc[-1]
    latest_volume = output["成交量"].iloc[-1]
    if pd.isna(mavol20) or mavol20 <= 0 or pd.isna(latest_volume):
        return None
    ratio = latest_volume / mavol20
    if ratio < 1.5:
        return None
    level = "明显放量" if ratio >= 2 else "放量"
    return _cached_common_row(output, ticker, provider, f"{level}，20日量比 {ratio:.2f}")


def _cached_common_row(output: pd.DataFrame, ticker: str, provider: HotSourceProvider, heat_text: str) -> dict[str, Any]:
    latest = output.iloc[-1]
    previous_close = output["收盘价"].iloc[-2] if len(output) >= 2 else pd.NA
    close = latest.get("收盘价")
    volume = latest.get("成交量", pd.NA)
    change = close / previous_close - 1 if pd.notna(close) and pd.notna(previous_close) and previous_close != 0 else pd.NA
    return {
        "代码": ticker,
        "名称": "",
        "来源网站": provider.来源网站,
        "来源页面": provider.来源页面,
        "来源分类": provider.来源分类,
        "入选原因": provider.入选原因,
        "热度说明": heat_text,
        "最新价格": close,
        "当日涨幅": change,
        "成交量": volume,
        "成交额": close * volume if pd.notna(close) and pd.notna(volume) else pd.NA,
        "市值": pd.NA,
    }


def _sort_number(value: Any) -> float:
    number = pd.to_numeric(value, errors="coerce")
    return float(number) if pd.notna(number) else -1.0
