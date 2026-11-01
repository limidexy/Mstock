from pathlib import Path

import pandas as pd

from src.features.required_columns import get_missing_feature_columns


项目根目录 = Path(__file__).resolve().parents[1]


def test_feature_sample_output_has_required_columns_and_excludes_benchmarks():
    """检查技术特征样例字段完整，并默认排除 QQQ 和 SPY。"""
    sample_path = 项目根目录 / "data" / "output" / "技术特征样例.csv"

    assert sample_path.exists(), "缺少技术特征样例文件：data/output/技术特征样例.csv"

    sample = pd.read_csv(sample_path, encoding="utf-8-sig")
    missing = get_missing_feature_columns(sample.columns.tolist())

    assert not missing, f"技术特征样例缺少字段：{missing}"
    assert len(sample.columns) >= 80
    assert "QQQ" not in set(sample["代码"])
    assert "SPY" not in set(sample["代码"])
