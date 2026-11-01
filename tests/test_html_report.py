from pathlib import Path

import pandas as pd
import pytest

from src.reports.html_report import (
    HTML主表字段,
    读取候选票,
    生成HTML报告,
    筛选HTML候选,
)


项目根目录 = Path(__file__).resolve().parents[1]


def test_html_report_generation_no_charts_contains_required_content(tmp_path):
    """HTML 报告可以离线生成，并包含主表格、卡片、风险标签和评分解释。"""
    result = 生成HTML报告(
        input_path=项目根目录 / "data" / "output" / "今日候选票.csv",
        cache_dir=项目根目录 / "data" / "cache" / "daily",
        output_path=tmp_path / "今日候选票.html",
        charts_dir=tmp_path / "charts",
        report_path=tmp_path / "HTML报告验收报告.md",
        failure_path=tmp_path / "HTML报告失败清单.csv",
        top=5,
        no_charts=True,
    )
    html = result.html_path.read_text(encoding="utf-8")

    assert result.html_path.exists()
    assert result.display_count == 5
    assert result.chart_count == 0
    assert result.contains_title
    assert result.contains_disclaimer
    assert result.contains_table
    assert result.contains_cards
    assert result.contains_risk_tags
    assert result.contains_score_explanation
    assert result.offline_ready
    assert "美股主升浪突破候选票报告" in html
    assert "本报告仅用于候选筛选和复盘，不构成买卖建议，不自动交易" in html
    assert 'id="candidateTable"' in html
    assert 'class="candidate-card' in html
    assert "当前结果只基于已缓存标的，不代表全市场" in html
    assert "http://" not in html and "https://" not in html
    assert 'data-search="QQQ' not in html and 'data-search="SPY' not in html


def test_html_filters_do_not_mutate_input_and_parameters_work():
    """HTML 筛选参数有效，且不原地修改输入 DataFrame。"""
    source = pd.read_csv(项目根目录 / "data" / "output" / "今日候选票.csv", encoding="utf-8-sig")
    original = source.copy(deep=True)

    top = 筛选HTML候选(source, top=3)
    min_score = 筛选HTML候选(source, min_score=65)
    min_grade = 筛选HTML候选(source, min_grade="B")

    pd.testing.assert_frame_equal(source, original)
    assert len(top) <= 3
    assert top["综合评分"].is_monotonic_decreasing
    if not min_score.empty:
        assert (min_score["综合评分"] >= 65).all()
    if not min_grade.empty:
        assert set(min_grade["等级"]).issubset({"B", "A", "A+"})


def test_html_chart_failure_does_not_block_report(tmp_path):
    """单只图表失败不影响 HTML 报告生成。"""
    source = pd.read_csv(项目根目录 / "data" / "output" / "今日候选票.csv", encoding="utf-8-sig").head(1).copy()
    source.loc[source.index[0], "代码"] = "MISSING_CACHE"
    input_path = tmp_path / "候选票.csv"
    source.to_csv(input_path, index=False, encoding="utf-8-sig")

    result = 生成HTML报告(
        input_path=input_path,
        cache_dir=tmp_path / "空缓存",
        output_path=tmp_path / "今日候选票.html",
        charts_dir=tmp_path / "charts",
        report_path=tmp_path / "HTML报告验收报告.md",
        failure_path=tmp_path / "HTML报告失败清单.csv",
    )
    failures = pd.read_csv(result.failure_path, encoding="utf-8-sig")

    assert result.html_path.exists()
    assert result.display_count == 1
    assert result.chart_failure_count == 1
    assert len(failures) == 1
    assert "生成图表" in failures.iloc[0]["失败阶段"]
    assert "图表暂不可用" in result.html_path.read_text(encoding="utf-8")


def test_missing_required_candidate_fields_raise_chinese_error(tmp_path):
    """候选票 CSV 缺少必要字段时抛出中文错误。"""
    source = pd.read_csv(项目根目录 / "data" / "output" / "今日候选票.csv", encoding="utf-8-sig")
    broken = source.drop(columns=["风险标签"])
    input_path = tmp_path / "缺字段候选票.csv"
    broken.to_csv(input_path, index=False, encoding="utf-8-sig")

    with pytest.raises(ValueError, match="候选票缺少必要字段"):
        读取候选票(input_path)


def test_html_main_table_fields_are_chinese():
    """HTML 主表字段全部为中文业务字段。"""
    assert "综合评分" in HTML主表字段
    assert "风险标签" in HTML主表字段
    assert "入选理由" in HTML主表字段
