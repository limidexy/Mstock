import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.scoring.scoring_pipeline import 评分输出字段


项目根目录 = Path(__file__).resolve().parents[1]


def test_scoring_sample_output_contains_required_fields_and_sorted():
    """评分样例 CSV 包含必要字段，并按综合评分降序。"""
    sample_path = 项目根目录 / "data" / "output" / "评分样例.csv"
    assert sample_path.exists(), "缺少评分样例，请先运行 scripts/生成评分样例.py"
    sample = pd.read_csv(sample_path, encoding="utf-8-sig")

    missing = [field for field in 评分输出字段 if field not in sample.columns]
    assert not missing
    assert sample["综合评分"].between(0, 100).all()
    assert sample["综合评分"].is_monotonic_decreasing
    assert sample["入选理由"].astype(str).str.strip().ne("").all()
    assert sample["风险标签"].astype(str).str.strip().ne("").all()
    assert sample["评分解释"].astype(str).str.strip().ne("").all()


def test_scoring_script_top_and_min_score_parameters(tmp_path):
    """评分脚本 top 和 min-score 参数有效。"""
    top_output = tmp_path / "评分_top10.csv"
    min_output = tmp_path / "评分_min65.csv"

    subprocess.run(
        [sys.executable, "scripts/生成评分样例.py", "--top", "10", "--output", str(top_output)],
        cwd=项目根目录,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "scripts/生成评分样例.py", "--min-score", "65", "--output", str(min_output)],
        cwd=项目根目录,
        check=True,
        capture_output=True,
        text=True,
    )

    top_df = pd.read_csv(top_output, encoding="utf-8-sig")
    min_df = pd.read_csv(min_output, encoding="utf-8-sig")

    assert len(top_df) <= 10
    if not min_df.empty:
        assert (min_df["综合评分"] >= 65).all()
