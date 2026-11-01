"""迁移样本一致性检查的回归测试。"""

from copy import deepcopy

import pytest

from scripts.迁移离线验收 import compare_snapshots


def test_snapshot_requires_identical_inputs_and_calculations():
    """容忍浮点误差，拒绝输入变化和评分变化。"""
    original = {"输入文件SHA256": {"测试": "相同输入"},
                "技术特征": [{"代码": "测试", "MA5": 1.23456789}],
                "评分": [{"代码": "测试", "综合评分": 65.0}]}
    restored = deepcopy(original)
    restored["技术特征"][0]["MA5"] += 1e-10
    compare_snapshots(restored, original)
    restored["评分"][0]["综合评分"] = 75.0
    with pytest.raises(AssertionError):
        compare_snapshots(restored, original)
    restored = deepcopy(original)
    restored["输入文件SHA256"]["测试"] = "不同输入"
    with pytest.raises(ValueError, match="输入校验值"):
        compare_snapshots(restored, original)
