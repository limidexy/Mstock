"""按事先固定协议检验存储股观察规则，不生成实盘指令、不承诺胜率。"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
import os
import random
from pathlib import Path
import statistics
import sys
import time
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
ASSETS = [
    {"代码": "000660.KS", "名称": "海力士韩股", "公司组": "海力士", "币种": "KRW", "美国市场": False},
    {"代码": "005930.KS", "名称": "三星电子", "公司组": "三星", "币种": "KRW", "美国市场": False},
    {"代码": "MU", "名称": "美光", "公司组": "美光", "币种": "USD", "美国市场": True},
    {"代码": "SNDK", "名称": "闪迪", "公司组": "闪迪", "币种": "USD", "美国市场": True, "最早日期": "2025-02-24"},
    {"代码": "SKHY", "名称": "海力士美股ADR", "公司组": "海力士", "币种": "USD", "美国市场": True, "最早日期": "2026-07-10"},
    {"代码": "7709.HK", "名称": "海力士港股杠杆产品", "公司组": "海力士", "币种": "HKD", "美国市场": False, "最早日期": "2025-10-16", "杠杆产品": True},
]


def load_protocol():
    text = (ROOT / "protocol.json").read_text(encoding="utf-8")
    return json.loads(text), hashlib.sha256(text.encode()).hexdigest()


def wilson(wins, n):
    if not n:
        return [0.0, 1.0]
    z = 1.959963984540054
    p = wins / n
    denominator = 1 + z*z/n
    center = (p + z*z/(2*n)) / denominator
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return [max(0, center-radius), min(1, center+radius)]


def check_bars(bars):
    seen = set()
    for b in bars:
        if b["date"] in seen:
            raise ValueError("发现重复日期：" + b["date"])
        seen.add(b["date"])
        if not all(math.isfinite(b[k]) and b[k] > 0 for k in ("o", "h", "l", "c")):
            raise ValueError("发现非正价格或无效数字：" + b["date"])
        tolerance = max(b[k] for k in ("o", "h", "l", "c"))*1e-7
        if b["l"] > min(b["o"], b["c"]) + tolerance or b["h"] < max(b["o"], b["c"]) - tolerance:
            raise ValueError("日线高低区间不包容开收盘：" + json.dumps(b, ensure_ascii=False))
    if bars != sorted(bars, key=lambda b: b["date"]):
        raise ValueError("日期顺序无效")


def wave_points(bars, span, min_move):
    out = []
    for i in range(span, len(bars)-span):
        b = bars[i]
        around = bars[i-span:i] + bars[i+1:i+span+1]
        high = all(b["h"] > x["h"] for x in around)
        low = all(b["l"] < x["l"] for x in around)
        if high == low:
            continue
        p = {"i": i, "price": b["h"] if high else b["l"], "kind": "H" if high else "L", "known": i+span}
        if not out:
            out.append(p)
        elif p["kind"] == out[-1]["kind"]:
            if (high and p["price"] > out[-1]["price"]) or (not high and p["price"] < out[-1]["price"]):
                out[-1] = p
        elif abs(p["price"]/out[-1]["price"]-1) >= min_move:
            out.append(p)
    return out


def latest_center(bars, protocol):
    ps = wave_points(bars, protocol["波段确认侧根数"], protocol["波段最小反向比例"])
    latest = None
    for i in range(3, len(ps)):
        p = ps[i-3:i+1]
        lows = [min(p[j]["price"], p[j+1]["price"]) for j in range(3)]
        highs = [max(p[j]["price"], p[j+1]["price"]) for j in range(3)]
        lo, hi = max(lows), min(highs)
        if lo < hi:
            latest = {"lo": lo, "hi": hi, "known": p[3]["known"]}
    return latest


def features(bars, protocol):
    e20 = e50 = None
    closes, ranges, e20s, result = [], [], [], []
    for i, b in enumerate(bars):
        e20 = b["c"] if e20 is None else b["c"]*2/21 + e20*19/21
        e50 = b["c"] if e50 is None else b["c"]*2/51 + e50*49/51
        e20s.append(e20)
        previous = bars[i-1]["c"] if i else b["c"]
        ranges.append(max(b["h"]-b["l"], abs(b["h"]-previous), abs(b["l"]-previous)))
        closes.append(b["c"])
        atr = statistics.fmean(ranges[-14:]) if i >= 13 else None
        regime = "历史不足未分类"
        if i >= 219:
            now = statistics.fmean(closes[-200:])
            old = statistics.fmean(closes[-220:-20])
            regime = "上涨环境" if previous > now and now > old else "下跌环境" if previous < now and now < old else "震荡环境"
        signals = {}
        if i >= 60 and atr:
            trend = e20 > e50
            if trend and b["c"] > max(x["h"] for x in bars[i-20:i]):
                signals["20日高点突破"] = {"stop": b["c"] - protocol["ATR风险倍数"]*atr}
            if trend and b["l"] <= e20 < b["c"] and b["c"] > b["o"] and e20 > e20s[i-5]:
                signals["趋势均线回踩"] = {"stop": b["c"] - protocol["ATR风险倍数"]*atr}
            center = latest_center(bars[:i], protocol)
            if center and center["known"] <= i-1 and previous <= center["hi"] < b["c"] and trend:
                signals["三段重叠突破"] = {"stop": center["lo"] - .1*atr, "区间下沿": center["lo"], "区间上沿": center["hi"]}
        result.append({"signals": signals, "atr": atr, "regime": regime})
    return result


def exit_on_bar(position, b, index, hold):
    # 日线无法确定同日触及顺序，优先按不利边界计算，不假定在最高最低点成交。
    if b["o"] <= position["stop"]:
        return b["o"], "不利跳空"
    if b["o"] >= position["target"]:
        return position["target"], "收益边界"
    if b["l"] <= position["stop"]:
        return position["stop"], "风险边界"
    if b["h"] >= position["target"]:
        return position["target"], "收益边界"
    if index-position["index"]+1 >= hold:
        return b["c"], "最长观察期结束"
    return None


def simulate(bars, feats, config, start, end, cost, leveraged=False):
    trades, curve = [], []
    position = None
    capital = 1.0
    for i, b in enumerate(bars):
        if not start <= b["date"] <= end:
            continue
        if position is None and i:
            signal = feats[i-1]["signals"].get(config["策略"])
            if signal:
                risk = b["o"]-signal["stop"]
                if .01 <= risk/b["o"] <= (.25 if leveraged else .12):
                    position = {"entry": b["o"], "stop": signal["stop"], "target": b["o"]+risk*config["盈亏倍数"], "index": i, "signal_date": bars[i-1]["date"], "entry_date": b["date"], "regime": feats[i-1]["regime"]}
        if position:
            outcome = exit_on_bar(position, b, i, config["最长持有日"])
            if outcome:
                price, reason = outcome
                gross = price/position["entry"]-1
                net = gross-cost
                trades.append({"信号日期": position["signal_date"], "开始日期": position["entry_date"], "结束日期": b["date"], "模拟起始价格": position["entry"], "模拟结束价格": price, "毛收益": gross, "净收益": net, "环境": position["regime"], "结束原因": reason})
                capital *= 1+net
                position = None
        mark = capital if position is None else capital*(b["c"]/position["entry"]-cost)
        curve.append({"日期": b["date"], "研究净值": mark})
    return {"trades": trades, "curve": curve, "open": int(position is not None)}


def stats(sim, extra_cost=0):
    values = [t["净收益"]-extra_cost for t in sim["trades"]]
    wins = sum(v > 1e-12 for v in values)
    positives = [v for v in values if v > 1e-12]
    negatives = [v for v in values if v < -1e-12]
    peak, drawdown = 1.0, 0.0
    for p in sim["curve"]:
        peak = max(peak, p["研究净值"])
        drawdown = max(drawdown, 1-p["研究净值"]/peak)
    return {"完成次数": len(values), "盈利次数": wins, "保本次数": sum(abs(v) <= 1e-12 for v in values), "净胜率": wins/len(values) if values else None, "胜率95%区间": wilson(wins, len(values)), "未结束按不赢处理的胜率区间": wilson(wins, len(values)+sim["open"]), "每次平均净收益": statistics.fmean(values) if values else None, "平均盈利": statistics.fmean(positives) if positives else None, "平均亏损": statistics.fmean(negatives) if negatives else None, "盈利亏损总额比": sum(positives)/abs(sum(negatives)) if negatives else None, "收盘盯市最大回撤": drawdown if sim["curve"] else None, "未结束次数": sim["open"]}


def monthly_blocks(trades, protocol, extra_cost=0):
    groups = {}
    for t in trades:
        key = t["开始日期"][:7]
        g = groups.setdefault(key, [0, 0, 0.0])
        value = t["净收益"]-extra_cost
        g[0] += 1; g[1] += int(value > 1e-12); g[2] += value
    if len(groups) < protocol["最低不同进入月份"]:
        return {"不同进入月份": len(groups), "月份区块胜率95%区间": None, "月份区块平均净收益95%区间": None}
    rng = random.Random(20261104)
    blocks = list(groups.values())
    rates, means = [], []
    for _ in range(protocol["月份区块重采样次数"]):
        samples = [rng.choice(blocks) for _ in blocks]
        n = sum(g[0] for g in samples)
        rates.append(sum(g[1] for g in samples)/n)
        means.append(sum(g[2] for g in samples)/n)
    rates.sort(); means.sort()
    a, b = int(len(rates)*.025), min(len(rates)-1, int(len(rates)*.975))
    return {"不同进入月份": len(groups), "月份区块胜率95%区间": [rates[a], rates[b]], "月份区块平均净收益95%区间": [means[a], means[b]]}


def accepted(summary, stress, calibrated, protocol):
    if not calibrated:
        return "没有通过训练验证筛选的候选，预设基线仅供探索"
    if summary["完成次数"] < protocol["单标的留出段最低完成次数"]:
        return "留出段样本不足，不能认定达到80%"
    block_interval = summary.get("月份区块胜率95%区间")
    passes = [summary["净胜率"] >= protocol["目标净胜率"], summary["未结束按不赢处理的胜率区间"][0] >= protocol["胜率95%区间下限门槛"], bool(block_interval) and block_interval[0] >= protocol["胜率95%区间下限门槛"], summary["每次平均净收益"] > 0, stress["每次平均净收益"] is not None and stress["每次平均净收益"] > 0, summary["盈利亏损总额比"] is not None and summary["盈利亏损总额比"] >= protocol["最低收益风险比指标"], summary["收盘盯市最大回撤"] <= protocol["收盘盯市最大回撤上限"]]
    return "历史留出检验初步满足，仍需未来模拟验证" if all(passes) else "未达到预设80%验收条件"


def analyze_asset(asset, bars, protocol):
    feats = features(bars, protocol)
    cost = protocol["杠杆产品单次往返成本假设"] if asset.get("杠杆产品") else protocol["普通股单次往返成本假设"]
    configs = [{"策略": strategy, "盈亏倍数": rr, "最长持有日": hold} for strategy, rr, hold in itertools.product(protocol["策略候选"], protocol["盈亏倍数候选"], protocol["最长持有交易日候选"])]
    candidates = []
    for config in configs:
        train = stats(simulate(bars, feats, config, *protocol["训练区间"], cost, asset.get("杠杆产品", False)))
        validation = stats(simulate(bars, feats, config, *protocol["验证区间"], cost, asset.get("杠杆产品", False)))
        candidates.append({"参数": config, "训练": train, "验证": validation})
    eligible = [c for c in candidates if c["训练"]["完成次数"] >= protocol["最低训练次数"] and c["验证"]["完成次数"] >= protocol["最低验证次数"] and c["训练"]["每次平均净收益"] > 0 and c["验证"]["每次平均净收益"] > 0]
    # 仅用训练与验证选择；严禁先看留出胜率再修改参数。
    chosen = max(eligible, key=lambda c: (c["验证"]["每次平均净收益"], -c["验证"]["收盘盯市最大回撤"]))["参数"] if eligible else {"策略": "20日高点突破", "盈亏倍数": 1.5, "最长持有日": 20}
    end = protocol["美国完整日期上限"] if asset["美国市场"] else protocol["亚洲完整日期上限"]
    start = protocol["留出区间"][0]
    sim = simulate(bars, feats, chosen, start, end, cost, asset.get("杠杆产品", False))
    summary = stats(sim)
    summary.update(monthly_blocks(sim["trades"], protocol))
    stress = stats(sim, extra_cost=cost*(protocol["成本压力倍数"]-1))
    stress.update(monthly_blocks(sim["trades"], protocol, extra_cost=cost*(protocol["成本压力倍数"]-1)))
    groups = {}
    for regime in ("上涨环境", "下跌环境", "震荡环境", "历史不足未分类"):
        subset = [t for t in sim["trades"] if t["环境"] == regime]
        groups[regime] = stats({"trades": subset, "curve": [], "open": 0})
    # 成本压力检查只重估同一组固定模拟记录的净收益，不把基础资金曲线回撤冒充压力回撤。
    stress.pop("收盘盯市最大回撤", None)
    diagnostics = {"训练次数达标候选数": sum(c["训练"]["完成次数"] >= protocol["最低训练次数"] for c in candidates), "验证次数达标候选数": sum(c["验证"]["完成次数"] >= protocol["最低验证次数"] for c in candidates), "两段次数均达标候选数": sum(c["训练"]["完成次数"] >= protocol["最低训练次数"] and c["验证"]["完成次数"] >= protocol["最低验证次数"] for c in candidates), "样本覆盖训练验证区间": bars[0]["date"] <= protocol["训练区间"][1] and bars[-1]["date"] >= protocol["验证区间"][0]}
    result = {**asset, "原始样本数": len(bars), "样本起点": bars[0]["date"], "样本终点": bars[-1]["date"], "训练验证合格候选数": len(eligible), "筛选诊断": diagnostics, "选定参数": chosen, "成本假设": cost, "留出区间": [start, end], "留出结果": summary, "成本加倍结果": stress, "分环境结果": groups, "状态": accepted(summary, stress, bool(eligible), protocol), "候选训练验证记录": candidates}
    return result, sim


def get_data(asset, protocol, raw_directory):
    import yfinance as yf
    ticker = asset["代码"]
    obj = yf.Ticker(ticker)
    frame = None
    for attempt in range(2):
        try:
            frame = obj.history(start=protocol["数据请求起点"], end="2026-11-04", interval="1d", auto_adjust=False, back_adjust=False, repair=False, actions=True, raise_errors=True, timeout=30)
            if not frame.empty:
                break
        except Exception:
            if attempt:
                raise
            time.sleep(2)
    if frame is None or frame.empty:
        raise ValueError("行情源未返回历史；不以短样本或模拟值补齐")
    cutoff = protocol["美国完整日期上限"] if asset["美国市场"] else protocol["亚洲完整日期上限"]
    bars, raw, excluded, pending_tail = [], [], 0, []
    selected_rows = []
    for index, row in frame.iterrows():
        date = index.date().isoformat()
        if date > cutoff or date < asset.get("最早日期", protocol["数据请求起点"]):
            excluded += 1
            continue
        selected_rows.append((date, row))
    for date, row in selected_rows:
        values = {k: float(row[col]) for k, col in (("o", "Open"), ("h", "High"), ("l", "Low"), ("c", "Close"))}
        adj = float(row.get("Adj Close", float("nan")))
        if not math.isfinite(adj) or adj <= 0:
            pending_tail.append(date)
            adj = None
        bars.append({"date": date, **{k: round(v, 6) for k, v in values.items()}})
        raw.append({"日期": date, "开盘价": values["o"], "最高价": values["h"], "最低价": values["l"], "收盘价": values["c"], "参考复权收盘价": adj, "成交量": float(row.get("Volume", 0)), "现金分红": float(row.get("Dividends", 0)), "拆股倍数": float(row.get("Stock Splits", 0))})
    source = "Yahoo Finance公开拆股调整OHLC，经yfinance读取"
    comparison = None
    if ticker.endswith(".KS"):
        if any(r["拆股倍数"] not in (0, 1) for r in raw):
            raise ValueError("韩股窗口内出现拆股，备用源价格口径需单独核对，暂停该标的")
        code = ticker.split('.')[0]
        url = "https://fchart.stock.naver.com/sise.nhn?symbol="+code+"&timeframe=day&count=1800&requestType=0"
        request = Request(url, headers={"User-Agent": "MstockResearch/1.0"})
        payload = urlopen(request, timeout=30).read()
        root = ET.fromstring(payload)
        local_bars = []
        for item in root.iter('item'):
            fields = item.attrib.get('data', '').split('|')
            if len(fields) < 6:
                continue
            stamp = fields[0]
            day = stamp[:4]+'-'+stamp[4:6]+'-'+stamp[6:8]
            if protocol["数据请求起点"] <= day <= cutoff:
                local_bars.append({"date": day, **dict(zip(('o','h','l','c'), map(float, fields[1:5])))})
        local_bars.sort(key=lambda b:b['date'])
        check_bars(local_bars)
        if len(local_bars) < 100:
            raise ValueError("韩股备用源没有足够可校验历史，未拼接或补值")
        by_date = {b['date']:b for b in bars}
        recent = [b for b in local_bars if b['date'] in by_date][-20:]
        mismatches = [b['date'] for b in recent if abs(b['c']/by_date[b['date']]['c']-1)>1e-5]
        if len(recent)<10 or mismatches:
            raise ValueError("韩股两源最近收盘口径未一致："+','.join(mismatches))
        comparison = {"对照来源": "Yahoo Finance", "最近对照日期数": len(recent), "收盘差异日期": mismatches, "原始备用源SHA256": hashlib.sha256(payload).hexdigest()}
        source = "Naver公开历史OHLC；最近20个交集日期与Yahoo收盘交叉核对"
        bars = local_bars
    check_bars(bars)
    if len(bars) < 65:
        raise ValueError("有效完整日线少于65根，无法做本协议的指标预热与评估")
    stale = (datetime.fromisoformat(cutoff)-datetime.fromisoformat(bars[-1]["date"])).days
    if stale > 5:
        raise ValueError("最新历史超过完成日期上限五天，需诊断是否缺失或停牌")
    path = raw_directory / (ticker + ".csv")
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(raw[0]))
        writer.writeheader(); writer.writerows(raw)
    used_path = raw_directory / (ticker + "_实际分析输入.csv")
    with used_path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=['date','o','h','l','c']);writer.writeheader();writer.writerows(bars)
    precision_count = sum(b["l"] > min(b["o"], b["c"]) or b["h"] < max(b["o"], b["c"]) for b in bars)
    audit = {"来源": source, "读取库版本": yf.__version__, "获取时间": datetime.now(timezone.utc).isoformat(), "原始市场时区": str(frame.index.tz), "频率": "日线", "原始输入校验SHA256": hashlib.sha256(path.read_bytes()).hexdigest(), "实际分析输入SHA256": hashlib.sha256(used_path.read_bytes()).hexdigest(), "备用源对照": comparison, "行数": len(bars), "首日": bars[0]["date"], "末日": bars[-1]["date"], "按上市日期及收盘上限剔除行数": excluded, "未使用的分红复权字段异常日期": pending_tail, "微小价格精度差行数": precision_count, "精度容差": "相对价格一千万分之一；实际OHLC保留六位小数，超限继续失败", "收益口径": "同一来源OHLC的价格收益，不计现金分红和汇率损益；不同于前两轮分红再投复权结果，禁止混用", "成交量说明": "留存用于校验，未解决跨来源量差异，当前规则不使用成交量作为信号"}
    return bars, audit


def markdown_report(report):
    lines = ["# 存储股多样本验证", "", "80%是验收目标，不是事先承诺。未达标、样本不足和来源失败均保留。", "", f"协议校验：{report['协议SHA256']}", "", "| 标的 | 完整日线 | 留出完成次数 | 净胜率 | 95%区间 | 每次平均净收益 | 状态 |", "| --- | ---: | ---: | ---: | --- | ---: | --- |"]
    for item in report["标的结果"]:
        if "留出结果" not in item:
            lines.append(f"| {item['代码']} | — | — | — | — | — | {item['状态']} |")
            continue
        s = item["留出结果"]
        rate = "无已完成记录" if s["净胜率"] is None else f"{s['净胜率']:.1%}"
        expected = "—" if s["每次平均净收益"] is None else f"{s['每次平均净收益']:.2%}"
        interval = "—" if not s["完成次数"] else f"{s['胜率95%区间'][0]:.1%}–{s['胜率95%区间'][1]:.1%}"
        lines.append(f"| {item['代码']} | {item['原始样本数']} | {s['完成次数']} | {rate} | {interval} | {expected} | {item['状态']} |")
    lines += ["", "## 阅读边界", "", "- 同公司不同市场不合并为独立胜率样本；分标的、分环境报告。", "- 训练2021至2022年，验证2023年，历史留出2024年至已完成日期。上市较晚者缺少训练验证时仅报告预设基线。", "- 选择股票时已知当前标的和近期行情，存在选择偏差；历史留出不能替代未来模拟观察。", "- 价格收益口径、成本、成交顺序均为明确研究假设，不能把结果称作真实账户收益。", "- 成本加倍只重估同一批完成记录，不虚报压力情况下的回撤。", "- 原始行情仅留在运行器临时目录，公开产物不包含整套行情缓存。", "- 不自动交易，不生成券商指令，不因不足80%就反复尝试新参数。"]
    return "\n".join(lines)+"\n"


def self_test():
    assert .70 < wilson(80, 100)[0] < .72
    check_bars([{"date": "2020-01-01", "o": 99980, "h": 100000, "l": 99950, "c": 100000.0001}])
    try:
        check_bars([{"date": "2020-01-01", "o": 99980, "h": 100000, "l": 99950, "c": 100005}])
        raise AssertionError("真实超限异常不应被容差放过")
    except ValueError:
        pass
    assert wilson(8, 10)[0] < wilson(80, 100)[0]
    p = {"entry": 100, "stop": 95, "target": 110, "index": 0}
    assert exit_on_bar(p, {"o": 100, "h": 112, "l": 94, "c": 106}, 0, 20) == (95, "风险边界")
    assert exit_on_bar(p, {"o": 90, "h": 99, "l": 89, "c": 96}, 1, 20) == (90, "不利跳空")
    assert exit_on_bar(p, {"o": 115, "h": 116, "l": 114, "c": 115}, 1, 20) == (110, "收益边界")
    assert exit_on_bar(p, {"o": 115, "h": 116, "l": 90, "c": 91}, 1, 20) == (110, "收益边界")
    flat = {"trades": [{"净收益": 0}, {"净收益": .01}, {"净收益": -.02}], "curve": [], "open": 1}
    assert stats(flat)["净胜率"] == 1/3
    assert stats(flat)["完成次数"] == 3
    assert stats(flat)["未结束次数"] == 1
    synthetic = [{"date": f"2026-01-0{i+1}", "o": 10, "h": h, "l": 8, "c": 10} for i, h in enumerate([11, 12, 16, 13, 12])]
    assert len(wave_points(synthetic[:4], 2, .035)) == 0
    assert wave_points(synthetic, 2, .035)[0]["known"] == 4
    bars = [{"date": f"2026-01-{i+1:02d}", "o": 100, "h": 101, "l": 99, "c": 100} for i in range(3)]
    feats = [{"signals": {"20日高点突破": {"stop": 95}}, "regime": "震荡环境"}, {"signals": {}, "regime": "震荡环境"}, {"signals": {}, "regime": "震荡环境"}]
    sim = simulate(bars, feats, {"策略": "20日高点突破", "盈亏倍数": 1.5, "最长持有日": 20}, "2026-01-01", "2026-01-03", .004)
    assert sim["open"] == 1 and len(sim["trades"]) == 0
    assert len(sim["curve"]) == 3
    changed = [dict(b) for b in bars]
    changed[1].update(o=105, h=106, l=104, c=105)
    changed[2].update(o=110, h=119, l=109, c=118)
    simulated = simulate(changed, feats, {"策略": "20日高点突破", "盈亏倍数": 1.5, "最长持有日": 2}, "2026-01-01", "2026-01-03", .004)
    assert simulated["trades"][0]["模拟起始价格"] == 105
    assert simulated["trades"][0]["开始日期"] == "2026-01-02"
    assert abs(simulated["trades"][0]["净收益"] - (118/105-1-.004)) < 1e-12
    protocol, _ = load_protocol()
    zero = stats({"trades": [], "curve": [], "open": 0})
    assert "不足" in accepted(zero, zero, True, protocol)
    print("边界测试通过：确认延迟、下一根开盘、未完成排除、保本不算赢、双触不利处理、跳空、胜率区间与样本门槛。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT/"outputs")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if not args.allow_network:
        parser.error("默认不联网；明确允许读取公开行情后才使用 --allow-network。")
    protocol, digest = load_protocol()
    out = args.output_dir
    raw = out/"raw-private"; public = out/"reports"
    raw.mkdir(parents=True, exist_ok=True); public.mkdir(parents=True, exist_ok=True)
    (public/"固定验证协议.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"协议SHA256": digest, "源码提交": os.environ.get("MSTOCK_RESEARCH_SOURCE_SHA", "本地检查未提供提交"), "整理时间": datetime.now(timezone.utc).isoformat(), "目标": "历史留出净胜率至少80%，并检查样本、区间、期望、成本和回撤", "注意": protocol["声明"], "标的结果": [], "整体结论": "尚未完成"}
    for asset in ASSETS:
        try:
            print("正在读取并检验："+asset["代码"], flush=True)
            bars, audit = get_data(asset, protocol, raw)
            result, sim = analyze_asset(asset, bars, protocol)
            result["数据审计"] = audit
            report["标的结果"].append(result)
            safe_name = asset["代码"]
            (public/(safe_name+"_模拟记录.json")).write_text(json.dumps(sim, ensure_ascii=False, indent=2), encoding="utf-8")
            print("已完成："+safe_name+"；完整日线"+str(len(bars))+"根；"+result["状态"], flush=True)
        except Exception as exc:
            report["标的结果"].append({**asset, "状态": "数据或验证失败，未以零收益冒充成功", "错误类别": type(exc).__name__, "说明": str(exc)[:250]})
            print("本标的未完成："+asset["代码"]+"；"+type(exc).__name__, flush=True)
    report["整体结论"] = "仅个别标的初步满足，仍不能保证未来80%" if any(x["状态"].startswith("历史留出检验初步满足") for x in report["标的结果"]) else "尚无规则取得达到80%的充分验证证据"
    (public/"验证结果.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (public/"验证摘要.md").write_text(markdown_report(report), encoding="utf-8")
    compact = {**report, "标的结果": [{k:v for k,v in x.items() if k != "候选训练验证记录"} for x in report["标的结果"]]}
    print("验证摘要开始", flush=True)
    print(json.dumps(compact, ensure_ascii=False, separators=(",", ":")), flush=True)
    print("验证摘要结束", flush=True)
    if all("留出结果" not in x for x in report["标的结果"]):
        raise SystemExit("所有标的数据或验证失败，不能报告本轮已经完成。")


if __name__ == "__main__":
    main()
