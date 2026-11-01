import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.扩大真实数据验证 import (
    生成严重问题,
    运行真实数据验证,
)
from src.data.cache import 统计缓存文件数量


项目根目录 = Path(__file__).resolve().parents[1]


def make_args(**overrides):
    """构造扩容验证参数。"""
    defaults = {
        "target_size": 20,
        "days": 300,
        "provider": "auto",
        "sleep_min": 0.0,
        "sleep_max": 0.0,
        "max_retries": 0,
        "top": 100,
        "min_score": 0.0,
        "skip_download": False,
        "skip_html": True,
        "dry_run": True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_dry_run_does_not_trigger_download():
    """dry-run 只生成候选池和计划，不新增缓存下载。"""
    before = 统计缓存文件数量(项目根目录 / "data" / "cache")
    context = 运行真实数据验证(make_args(dry_run=True, skip_download=False))
    after = 统计缓存文件数量(项目根目录 / "data" / "cache")

    assert context.dry_run is True
    assert context.尝试下载数量 == 0
    assert before == after
    assert "dry-run 模式未执行真实下载" in context.严重问题


def test_target_size_over_500_exits_with_chinese_message():
    """target-size 超过500时中文提示并退出。"""
    completed = subprocess.run(
        [sys.executable, "scripts/扩大真实数据验证.py", "--target-size", "501", "--dry-run"],
        cwd=项目根目录,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "目标规模超过500" in completed.stderr or "目标规模超过500" in completed.stdout


def test_skip_download_can_generate_candidates_from_existing_cache():
    """skip-download 可以基于已有缓存继续生成候选票。"""
    context = 运行真实数据验证(make_args(dry_run=False, skip_download=True, skip_html=True))

    assert context.skip_download is True
    assert context.尝试下载数量 == 0
    assert context.今日候选票数量 > 0
    assert context.候选票路径.exists()
    assert context.待校对路径.exists()


def test_validation_report_contains_grade_distribution_and_top20():
    """真实候选池验证报告包含等级分布和 Top 20 摘要。"""
    context = 运行真实数据验证(make_args(dry_run=False, skip_download=True, skip_html=True))
    report_path = 项目根目录 / "data" / "output" / "真实候选池验证报告.md"
    report = report_path.read_text(encoding="utf-8")

    assert context.今日候选票数量 > 0
    assert "等级分布" in report
    assert "Top 20 摘要" in report
    assert "当前结果只基于已缓存或本轮已下载标的" in report


def test_missing_benchmark_is_reported_as_severe_issue():
    """QQQ/SPY 缺失会进入严重问题。"""
    issues = 生成严重问题(
        qqq_exists=False,
        spy_exists=False,
        cache_before=100,
        cache_after=100,
        attempted=0,
        success=0,
        failure=0,
        candidate_count=10,
        html_generated=True,
        dry_run=False,
        skip_html=False,
    )

    assert "QQQ 缺失" in issues
    assert "SPY 缺失" in issues


def test_target_size_validation_raises_chinese_error():
    """函数层面也会拒绝超过500的目标规模。"""
    with pytest.raises(ValueError, match="目标规模超过500"):
        运行真实数据验证(make_args(target_size=501))


def test_validation_output_csv_has_chinese_columns():
    """skip-download 后生成的候选票仍保持中文字段。"""
    运行真实数据验证(make_args(dry_run=False, skip_download=True, skip_html=True))
    candidates = pd.read_csv(项目根目录 / "data" / "output" / "今日候选票.csv", encoding="utf-8-sig")

    assert "综合评分" in candidates.columns
    assert "入选理由" in candidates.columns
