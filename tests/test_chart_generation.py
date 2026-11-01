from pathlib import Path

import pandas as pd

from src.reports.chart import 批量生成走势图, 生成单票走势图


项目根目录 = Path(__file__).resolve().parents[1]


def test_single_chart_generation_creates_png(tmp_path):
    """单只股票走势图可以生成 PNG。"""
    result = 生成单票走势图(
        ticker="AA",
        cache_dir=项目根目录 / "data" / "cache" / "daily",
        charts_dir=tmp_path,
        days=30,
    )

    assert result.success
    assert result.chart_path is not None
    assert result.chart_path.exists()
    assert result.chart_path.suffix.lower() == ".png"
    assert result.chart_path.stat().st_size > 0


def test_missing_cache_chart_failure_is_returned_not_raised(tmp_path):
    """缺少单只行情缓存时返回中文失败原因，不抛出异常。"""
    result = 生成单票走势图(
        ticker="不存在",
        cache_dir=tmp_path / "空缓存",
        charts_dir=tmp_path / "charts",
    )

    assert result.success is False
    assert result.chart_path is None
    assert "缺少行情缓存文件" in str(result.failure_reason)


def test_batch_chart_generation_records_failures(tmp_path):
    """批量图表生成时单只失败不影响其他标的。"""
    candidates = pd.DataFrame({"代码": ["AA", "不存在"]})

    chart_paths, failures = 批量生成走势图(
        candidates=candidates,
        cache_dir=项目根目录 / "data" / "cache" / "daily",
        charts_dir=tmp_path / "charts",
        days=30,
    )

    assert "AA" in chart_paths
    assert len(failures) == 1
    assert failures.iloc[0]["失败阶段"] == "生成图表"
