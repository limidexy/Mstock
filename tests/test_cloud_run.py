"""云端试运行的授权、数据完整性、日期对齐和输出隔离检查。"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scripts import 云端试运行 as cloud


固定时间 = datetime(2026, 11, 2, 13, 0, tzinfo=timezone.utc)


def 样例日线(ticker="AAPL", end="2026-10-30", rows=160):
    """独立模拟样本只用于测试，不会当作真实行情发布。"""
    dates = pd.bdate_range(end=end, periods=rows)
    growth = 0.0003 if ticker == "SPY" else 0.0005 if ticker == "QQQ" else 0.002
    close = 50 * (1 + growth) ** np.arange(rows)
    return pd.DataFrame({
        "日期": dates.strftime("%Y-%m-%d"), "代码": ticker,
        "开盘价": close * 0.999, "最高价": close * 1.0001,
        "最低价": close * 0.998, "收盘价": close, "复权收盘价": close,
        "成交量": [1_000_000] * (rows - 1) + [3_000_000],
        "数据来源": "测试模拟数据", "更新时间": "2026-11-02 00:00:00",
    })


def 模拟下载器(monkeypatch, *, missing=(), stale=()):
    """替换网络边界，内部继续使用真实特征、评分与HTML代码。"""
    monkeypatch.setattr(cloud, "创建数据源", lambda *args, **kwargs: object())

    def download(provider, tickers, *, cache_dir, failure_path, **kwargs):
        directory = Path(cache_dir) / "daily"
        directory.mkdir(parents=True)
        failures = []
        for ticker in tickers:
            if ticker in missing:
                failures.append({"代码": ticker, "失败原因": "模拟下载失败", "更新时间": ""})
                continue
            end = "2026-10-29" if ticker in stale else "2026-10-30"
            样例日线(ticker, end).to_csv(directory / f"{ticker}.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(failures, columns=["代码", "失败原因", "更新时间"]).to_csv(failure_path, index=False, encoding="utf-8-sig")
        return SimpleNamespace(成功数量=len(tickers)-len(failures), 失败数量=len(failures))

    monkeypatch.setattr(cloud, "批量更新日线缓存", download)


def test_network_requires_explicit_authorization(tmp_path, monkeypatch):
    """缺少明确授权时，在接触下载器和创建结果目录之前拒绝。"""
    def forbidden(*args, **kwargs):
        pytest.fail("未授权时不应接触网络边界。")
    monkeypatch.setattr(cloud, "创建数据源", forbidden)
    with pytest.raises(PermissionError, match="尚未允许联网"):
        cloud.运行云端试运行(tickers="AAPL", output_dir=tmp_path / "report")
    assert not (tmp_path / "report").exists()


@pytest.mark.parametrize("text", ["../AAPL", "AAPL;echo", "$(whoami)", "QQQ,SPY", ",".join(f"T{i}" for i in range(31))])
def test_tickers_reject_unsafe_or_empty_requests(text):
    """拒绝路径、命令文本、只有基准的请求和过大请求。"""
    with pytest.raises(ValueError):
        cloud.解析试运行代码(text)


def test_nonempty_output_is_preserved(tmp_path):
    """已有结果目录在任何下载发生前被保护。"""
    old = tmp_path / "人工校对.csv"
    old.write_text("不可覆盖", encoding="utf-8")
    with pytest.raises(FileExistsError):
        cloud.运行云端试运行(tickers="AAPL", output_dir=tmp_path, allow_network=True, now=固定时间)
    assert old.read_text(encoding="utf-8") == "不可覆盖"


def test_incomplete_day_is_excluded():
    """纽约17点前不会把当日尚未完成的日线当成收盘行情。"""
    cutoff = cloud.获取已收盘日期上限(固定时间)
    assert str(cutoff.date()) == "2026-11-01"
    result = cloud.校验完整日线(样例日线(end="2026-11-02"), "AAPL", cutoff)
    assert result["日期"].iloc[-1] == "2026-10-30"


@pytest.mark.parametrize("problem", ["零价格", "高低异常", "重复日期", "历史不足", "代码不一致"])
def test_damaged_data_is_rejected(problem):
    """拒绝无法安全参与计算的日线，而不是为通过试运行修数值。"""
    frame = 样例日线()
    if problem == "零价格":
        frame.loc[0, "最低价"] = 0
    elif problem == "高低异常":
        frame.loc[0, "最高价"] = 1
    elif problem == "重复日期":
        frame.loc[1, "日期"] = frame.loc[0, "日期"]
    elif problem == "历史不足":
        frame = frame.tail(80)
    else:
        frame.loc[0, "代码"] = "OTHER"
    with pytest.raises(ValueError):
        cloud.校验完整日线(frame, "AAPL", pd.Timestamp("2026-11-01"))


@pytest.mark.parametrize("case", ["缺少基准", "基准错日", "基准过旧"])
def test_missing_unaligned_or_stale_benchmarks_stop_scoring(case):
    """没有新鲜且日期一致的双基准就停止计算。"""
    frames = {"QQQ": 样例日线("QQQ"), "SPY": 样例日线("SPY")}
    if case == "缺少基准":
        del frames["QQQ"]
    elif case == "基准错日":
        frames["SPY"] = 样例日线("SPY", "2026-10-29")
    else:
        frames = {ticker: 样例日线(ticker, "2026-10-01") for ticker in ("QQQ", "SPY")}
    with pytest.raises(ValueError):
        cloud.确定基准日期(frames, pd.Timestamp("2026-11-01"))


def test_partial_network_result_generates_real_pipeline_report(tmp_path, monkeypatch):
    """部分下载失败时只计算同日有效样本，报告与图表由真实管线生成。"""
    模拟下载器(monkeypatch, missing=("FAIL",), stale=("OLD",))
    output = tmp_path / "report"
    summary = cloud.运行云端试运行(
        tickers="AAPL,OLD,FAIL", output_dir=output, allow_network=True, now=固定时间,
    )
    assert summary["运行状态"] == "部分接通"
    assert summary["下载成功数量"] == 4
    assert summary["下载失败数量"] == 1
    assert summary["评分输出数量"] == 1
    assert summary["排除股票"] == ["OLD", "FAIL"]
    assert summary["行情基准日期"] == "2026-10-30"
    assert summary["图表数量"] == 1
    html = (output / "index.html").read_text(encoding="utf-8")
    assert "云端小批量试运行" in html and "2026-10-30" in html
    assert "QQQ 最近" not in html
    assert (output / "charts/AAPL.png").is_file()
    assert not (output / "cache").exists()
    assert not list(output.rglob("QQQ.csv"))
    assert pd.read_csv(output / "候选票.csv", encoding="utf-8-sig")["代码"].tolist() == ["AAPL"]


def test_unavailable_benchmark_saves_failure_without_report(tmp_path, monkeypatch):
    """网络不可用时保留失败证据，不生成假的成功页面。"""
    模拟下载器(monkeypatch, missing=("QQQ",))
    output = tmp_path / "report"
    with pytest.raises(ValueError, match="基准"):
        cloud.运行云端试运行(tickers="AAPL", output_dir=output, allow_network=True, now=固定时间)
    assert (output / "运行摘要.json").is_file()
    assert "失败" in (output / "运行说明.md").read_text(encoding="utf-8")
    assert not (output / "index.html").exists()
