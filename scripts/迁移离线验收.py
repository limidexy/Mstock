"""只读检查本地行情、抽样公式及迁移前后计算一致性，不联网。"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

import pandas as pd

from scripts.生成技术特征样例 import 计算单票特征
from src.features.required_columns import get_required_feature_columns
from src.reports.html_report import 生成HTML报告
from src.scoring.scoring_pipeline import score_feature_dataframe_with_failures


def collect_snapshot(project: Path) -> dict:
    """校验所有缓存并抽取固定三票的最新特征和评分。"""
    cache = project / "data/cache/daily"
    files = sorted(cache.glob("*.csv"))
    if not files:
        raise ValueError("验收失败：没有行情缓存，请先恢复独立数据备份。")
    errors, date_counts = [], Counter()
    required = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "数据来源"]
    for path in files:
        try:
            daily = pd.read_csv(path, encoding="utf-8-sig")
            missing = set(required) - set(daily.columns)
            if daily.empty or missing:
                raise ValueError(f"空表或缺少字段：{sorted(missing)}")
            dates = pd.to_datetime(daily["日期"], errors="raise")
            if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
                raise ValueError("日期有缺失、重复或非升序")
            numeric = daily[["开盘价", "最高价", "最低价", "收盘价", "成交量"]].apply(pd.to_numeric, errors="coerce")
            if numeric.isna().any().any():
                raise ValueError("价格或成交量缺失")
            if (numeric[["开盘价", "最高价", "最低价", "收盘价"]] <= 0).any().any() or (numeric["成交量"] < 0).any():
                raise ValueError("价格非正或成交量为负")
            date_counts[dates.iloc[-1].strftime("%Y-%m-%d")] += 1
        except Exception as exc:
            errors.append({"代码": path.stem, "错误": str(exc)})
    tickers = ["AA", "AAPL", "NBIS", "QQQ", "SPY"]
    inputs, frames = {}, {}
    for ticker in tickers:
        path = cache / f"{ticker}.csv"
        if not path.exists():
            raise ValueError(f"验收失败：固定复核样本缓存缺失：{ticker}")
        inputs[ticker] = hashlib.sha256(path.read_bytes()).hexdigest()
        frames[ticker] = pd.read_csv(path, encoding="utf-8-sig")
    rows = [计算单票特征(frames[ticker], frames["QQQ"], frames["SPY"])
            .tail(1)[get_required_feature_columns()] for ticker in tickers[:3]]
    features = pd.concat(rows, ignore_index=True)
    scored = score_feature_dataframe_with_failures(features)
    if not scored.failures.empty:
        raise ValueError("验收失败：固定样本评分出现失败。")
    return {"Python版本": platform.python_version(),
            "核心依赖": {name: importlib.metadata.version(name) for name in ("pandas", "numpy")},
            "缓存数量": len(files), "缓存异常": errors, "最新日期分布": dict(sorted(date_counts.items())),
            "输入文件SHA256": inputs,
            "技术特征": json.loads(features.to_json(orient="records", force_ascii=False)),
            "评分": json.loads(scored.scored.to_json(orient="records", force_ascii=False))}


def compare_snapshots(snapshot: dict, reference: dict) -> None:
    """先校验输入字节，再以浮点容差比较所有样本特征和评分。"""
    if snapshot["输入文件SHA256"] != reference["输入文件SHA256"]:
        raise ValueError("一致性验收失败：行情输入校验值与基线不同，不能直接比较。")
    for key in ("技术特征", "评分"):
        pd.testing.assert_frame_equal(pd.DataFrame(snapshot[key]), pd.DataFrame(reference[key]),
                                      check_dtype=False, check_exact=False, rtol=1e-8, atol=1e-8)


def main() -> int:
    """生成独立验收结果和报告，不改写历史正式报表。"""
    parser = argparse.ArgumentParser(description="离线检查缓存、抽样计算与本地HTML，不联网、不交易。")
    parser.add_argument("--project", type=Path, default=项目根目录, help="待验收项目目录。")
    parser.add_argument("--output-dir", type=Path, required=True, help="独立验收输出目录。")
    parser.add_argument("--reference", type=Path, help="旧环境计算基线JSON。")
    parser.add_argument("--no-html", action="store_true", help="只生成计算基线，不生成HTML。")
    args = parser.parse_args()
    try:
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        snapshot = collect_snapshot(args.project.resolve())
        if args.reference:
            compare_snapshots(snapshot, json.loads(args.reference.read_text(encoding="utf-8")))
        (output / "计算基线.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        html_status = "未执行"
        if not args.no_html:
            result = 生成HTML报告(
                input_path=args.project / "data/output/今日候选票.csv",
                cache_dir=args.project / "data/cache/daily", output_path=output / "离线候选验收.html",
                charts_dir=output / "html_assets/charts", report_path=output / "HTML验收.md",
                failure_path=output / "HTML失败.csv", top=3, no_charts=False)
            if result.display_count != 3 or result.chart_count != 3 or not result.offline_ready:
                raise ValueError("离线HTML或三张图表验收未通过。")
            html_status = "离线HTML与三张图表生成通过"
        report = ["# 迁移离线验收结果", "", f"- Python版本：{snapshot['Python版本']}",
                  f"- 行情缓存：{snapshot['缓存数量']}个，异常文件：{len(snapshot['缓存异常'])}个。",
                  "- 固定复核样本：AA、AAPL、NBIS；基准：QQQ、SPY。",
                  f"- 跨环境计算一致性：{'通过，全部样本特征与评分在容差内一致' if args.reference else '已生成基线，尚未比较'}。",
                  f"- 图表报告：{html_status}。", "- 未联网、未下载行情、未执行交易。",
                  "- 未发现回测引擎，本次是研究筛选验收，不是回测验收。", "", "## 缓存最新日期分布", ""]
        report.extend(f"- {day}：{count}个" for day, count in snapshot["最新日期分布"].items())
        report.extend(["", "## 缓存异常", ""])
        report.extend(f"- {row['代码']}：{row['错误']}" for row in snapshot["缓存异常"])
        if not snapshot["缓存异常"]:
            report.append("- 无")
        (output / "迁移离线验收结果.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        if snapshot["缓存异常"]:
            print(f"迁移离线验收已完成，存在{len(snapshot['缓存异常'])}个缓存异常，请人工处理：{output}")
            return 2
        print(f"迁移离线验收通过：{output}")
        return 0
    except Exception as exc:
        print(f"迁移离线验收失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
