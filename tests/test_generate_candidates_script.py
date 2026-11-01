import subprocess
import sys
from pathlib import Path

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]


def run_candidate_script(tmp_path, *extra_args):
    """运行候选票脚本，并返回输出路径。"""
    output_path = tmp_path / "今日候选票.csv"
    review_path = tmp_path / "待校对.csv"
    report_path = tmp_path / "候选票生成报告.md"
    command = [
        sys.executable,
        "scripts/生成今日候选.py",
        "--output",
        str(output_path),
        "--review-output",
        str(review_path),
        "--report",
        str(report_path),
        *extra_args,
    ]
    completed = subprocess.run(command, cwd=项目根目录, check=True, capture_output=True, text=True)
    assert "今日候选票已生成" in completed.stdout or "今日候选票已生成" in completed.stderr
    return output_path, review_path, report_path, 项目根目录 / "data" / "output" / "候选票失败清单.csv"


def test_candidate_script_top_report_and_default_exclusion(tmp_path):
    """脚本 top 参数、报告内容和默认排除基准有效。"""
    output_path, review_path, report_path, failure_path = run_candidate_script(tmp_path, "--top", "5")

    candidates = pd.read_csv(output_path, encoding="utf-8-sig")
    review = pd.read_csv(review_path, encoding="utf-8-sig")
    failures = pd.read_csv(failure_path, encoding="utf-8-sig")
    report = report_path.read_text(encoding="utf-8")

    assert len(candidates) <= 5
    assert not {"QQQ", "SPY"}.intersection(set(candidates["代码"]))
    assert candidates["综合评分"].is_monotonic_decreasing
    assert candidates["排名"].tolist() == list(range(1, len(candidates) + 1))
    assert len(review) == len(candidates)
    assert failures.columns.tolist() == ["代码", "失败阶段", "失败原因"]
    assert "Top 10 摘要" in report
    assert "当前结果只基于已缓存标的，不代表全市场" in report


def test_candidate_script_min_score_and_min_grade(tmp_path):
    """脚本 min-score 和 min-grade 参数有效。"""
    min_score_output, _, _, _ = run_candidate_script(tmp_path / "score", "--top", "20", "--min-score", "65")
    min_grade_output, _, _, _ = run_candidate_script(tmp_path / "grade", "--top", "20", "--min-grade", "B")

    min_score_df = pd.read_csv(min_score_output, encoding="utf-8-sig")
    min_grade_df = pd.read_csv(min_grade_output, encoding="utf-8-sig")

    if not min_score_df.empty:
        assert (min_score_df["综合评分"] >= 65).all()
    if not min_grade_df.empty:
        assert set(min_grade_df["等级"]).issubset({"B", "A", "A+"})


def test_candidate_script_include_benchmark_can_output_qqq_spy(tmp_path):
    """传入 include-benchmark 时可以输出 QQQ、SPY。"""
    output_path, _, _, _ = run_candidate_script(tmp_path, "--top", "100", "--include-benchmark")

    candidates = pd.read_csv(output_path, encoding="utf-8-sig")

    assert {"QQQ", "SPY"}.issubset(set(candidates["代码"]))


def test_candidate_script_missing_stock_pool_still_succeeds(tmp_path):
    """股票池元数据缺失时脚本仍能生成输出和报告。"""
    output_path, _, report_path, _ = run_candidate_script(
        tmp_path,
        "--top",
        "5",
        "--stock-pool",
        str(tmp_path / "不存在的股票池.csv"),
    )

    candidates = pd.read_csv(output_path, encoding="utf-8-sig")
    report = report_path.read_text(encoding="utf-8")

    assert len(candidates) <= 5
    assert "股票池元数据不存在" in report
