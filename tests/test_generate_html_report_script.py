import subprocess
import sys
import re
from pathlib import Path

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]


def run_html_script(tmp_path, *extra_args):
    """运行 HTML 报告脚本并返回输出路径。"""
    output_path = tmp_path / "今日候选票.html"
    charts_dir = tmp_path / "charts"
    report_path = tmp_path / "HTML报告验收报告.md"
    command = [
        sys.executable,
        "scripts/生成HTML报告.py",
        "--output",
        str(output_path),
        "--charts-dir",
        str(charts_dir),
        "--report",
        str(report_path),
        *extra_args,
    ]
    completed = subprocess.run(command, cwd=项目根目录, check=True, capture_output=True, text=True)
    assert "HTML 报告已生成" in completed.stdout or "HTML 报告已生成" in completed.stderr
    return output_path, charts_dir, report_path, 项目根目录 / "data" / "output" / "HTML报告失败清单.csv"


def test_html_script_no_charts_outputs_files_and_report(tmp_path):
    """脚本 no-charts 参数有效，并生成 HTML、报告和失败清单。"""
    output_path, charts_dir, report_path, failure_path = run_html_script(tmp_path, "--top", "5", "--no-charts")

    html = output_path.read_text(encoding="utf-8")
    report = report_path.read_text(encoding="utf-8")
    failures = pd.read_csv(failure_path, encoding="utf-8-sig")

    assert output_path.exists()
    assert charts_dir.exists()
    assert report_path.exists()
    assert failure_path.exists()
    assert "图表暂不可用" in html
    assert '<img class="chart"' not in html
    assert "Top" not in report
    assert "HTML 展示候选数量：5" in report
    assert failures.columns.tolist() == ["代码", "失败阶段", "失败原因"]


def test_html_script_top_min_score_and_min_grade(tmp_path):
    """脚本 top、min-score、min-grade 参数有效。"""
    top_output, _, _, _ = run_html_script(tmp_path / "top", "--top", "3", "--no-charts")
    score_output, _, score_report, _ = run_html_script(tmp_path / "score", "--min-score", "65", "--no-charts")
    grade_output, _, grade_report, _ = run_html_script(tmp_path / "grade", "--min-grade", "B", "--no-charts")

    top_html = top_output.read_text(encoding="utf-8")
    score_html = score_output.read_text(encoding="utf-8")
    grade_html = grade_output.read_text(encoding="utf-8")
    score_cards = re.findall(r'<article class="candidate-card[^>]+data-score="([^"]+)"', score_html)
    grade_cards = re.findall(r'<article class="candidate-card[^>]+data-grade="([^"]+)"', grade_html)

    assert top_html.count('class="candidate-card') == 3
    assert score_cards
    assert grade_cards
    assert all(float(score) >= 65 for score in score_cards)
    assert set(grade_cards).issubset({"B", "A", "A+"})
    assert f"HTML 展示候选数量：{len(score_cards)}" in score_report.read_text(encoding="utf-8")
    assert f"HTML 展示候选数量：{len(grade_cards)}" in grade_report.read_text(encoding="utf-8")
    assert "AA" in score_html
    assert "AA" in grade_html


def test_html_script_default_generates_charts(tmp_path):
    """脚本默认生成本地图表。"""
    output_path, charts_dir, report_path, _ = run_html_script(tmp_path, "--top", "2")

    html = output_path.read_text(encoding="utf-8")
    report = report_path.read_text(encoding="utf-8")
    pngs = list(charts_dir.glob("*.png"))

    assert len(pngs) == 2
    assert '<img class="chart"' in html
    assert "生成图表数量：2" in report
    assert "http://" not in html and "https://" not in html
