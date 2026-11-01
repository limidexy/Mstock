from pathlib import Path
import re


项目根目录 = Path(__file__).resolve().parents[1]


def test_project_structure_exists():
    """检查项目骨架中的核心目录和文件是否存在。"""
    required_paths = [
        "AGENTS.md",
        "README.md",
        "requirements.txt",
        ".gitignore",
        ".env.example",
        "docs/策略说明.md",
        "docs/截图风格总结.md",
        "docs/中文字段说明.md",
        "docs/风险标签说明.md",
        "docs/数据源说明.md",
        "docs/校对流程.md",
        "config/系统配置.yml",
        "config/评分权重.yml",
        "config/数据源配置.example.yml",
        "data/raw",
        "data/processed",
        "data/cache",
        "data/review",
        "data/output",
        "src/__init__.py",
        "src/data/__init__.py",
        "src/data/universe.py",
        "src/data/providers.py",
        "src/data/yfinance_provider.py",
        "src/data/stooq_provider.py",
        "src/data/cache.py",
        "src/data/universe_selection.py",
        "src/data/web_hot_sources.py",
        "src/data/hot_universe.py",
        "src/features/__init__.py",
        "src/features/moving_average.py",
        "src/features/macd.py",
        "src/features/volume.py",
        "src/features/relative_strength.py",
        "src/features/breakout.py",
        "src/features/risk.py",
        "src/features/required_columns.py",
        "src/scoring/__init__.py",
        "src/scoring/similarity_score.py",
        "src/scoring/main_wave_score.py",
        "src/scoring/risk_penalty.py",
        "src/reports/__init__.py",
        "src/reports/csv_report.py",
        "src/reports/review_report.py",
        "src/reports/html_report.py",
        "src/reports/chart.py",
        "src/review/__init__.py",
        "src/review/review_loader.py",
        "src/review/feedback_analysis.py",
        "src/utils/__init__.py",
        "src/utils/logger.py",
        "src/utils/chinese.py",
        "scripts/更新股票池.py",
        "scripts/更新行情数据.py",
        "scripts/生成技术特征样例.py",
        "scripts/验收技术特征数值.py",
        "scripts/生成评分样例.py",
        "scripts/生成今日候选.py",
        "scripts/生成HTML报告.py",
        "scripts/构建下载候选池.py",
        "scripts/扩大真实数据验证.py",
        "scripts/诊断单票.py",
        "scripts/生成网上热度池.py",
        "scripts/更新网上热度池行情.py",
        "scripts/每日网上热度选票流程.py",
        "scripts/根据校对分析偏好.py",
        "tests/test_project_structure.py",
        "tests/test_chinese_output.py",
        "tests/test_html_report.py",
        "tests/test_chart_generation.py",
        "tests/test_generate_html_report_script.py",
        "tests/test_universe_selection.py",
        "tests/test_expand_real_data_validation.py",
        "tests/test_web_hot_sources.py",
        "tests/test_hot_universe_web.py",
        "tests/test_generate_web_hot_pool.py",
        "tests/test_update_web_hot_pool_data.py",
        "tests/test_daily_web_hot_workflow.py",
    ]

    missing_paths = [path for path in required_paths if not (项目根目录 / path).exists()]

    assert not missing_paths, f"缺少项目路径：{missing_paths}"


def test_requirements_contains_basic_dependencies():
    """检查依赖清单包含基础 Python 工程依赖。"""
    expected_dependencies = {
        "pandas",
        "numpy",
        "yfinance",
        "requests",
        "pyyaml",
        "matplotlib",
        "pytest",
        "jinja2",
        "tqdm",
        "python-dotenv",
        "lxml",
    }
    requirements = (项目根目录 / "requirements.txt").read_text(encoding="utf-8")
    actual_dependencies = {
        re.split(r"[<>=!~\[]", line.strip().lower(), maxsplit=1)[0]
        for line in requirements.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    missing_dependencies = expected_dependencies - actual_dependencies

    assert not missing_dependencies, f"依赖清单缺少：{sorted(missing_dependencies)}"


def test_core_utils_modules_can_be_imported():
    """检查中文工具模块可以正常导入。"""
    from src.utils import chinese, logger

    assert chinese.get_candidate_fields()
    assert logger.get_logger("Mstock测试日志")
