"""本地迁移备份测试，不读取真实数据。"""

import json

import pytest

from scripts.迁移数据备份 import create_backup, verify_backup


def test_backup_verifies_data_without_credentials(tmp_path):
    """保留中文校对文件，根目录凭据和环境不会进入压缩包。"""
    root = tmp_path / "项目"
    (root / "data/review").mkdir(parents=True)
    (root / "data/review/校对.csv").write_text("代码,我的校对\n测试,像\n", encoding="utf-8-sig")
    (root / ".env").write_text("测试私人配置", encoding="utf-8")
    manifest = create_backup(root, tmp_path / "备份")
    assert verify_backup(manifest) == 1
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    assert metadata["文件"][0]["相对路径"] == "data/review/校对.csv"
    assert metadata["文件"][0]["SHA256"]
    with pytest.raises(ValueError, match="禁止覆盖"):
        create_backup(root, manifest.parent)


def test_backup_detects_tampering_and_rejects_nested_output(tmp_path):
    """检测备份损坏，拒绝把压缩包写回待备份数据目录。"""
    (tmp_path / "data").mkdir()
    (tmp_path / "data/测试.csv").write_text("中文", encoding="utf-8")
    with pytest.raises(ValueError, match="不能位于数据目录"):
        create_backup(tmp_path, tmp_path / "data/备份")
    manifest = create_backup(tmp_path, tmp_path / "备份")
    archive = manifest.parent / "Mstock_本地数据.zip"
    archive.write_bytes(archive.read_bytes() + b"broken")
    with pytest.raises(ValueError, match="校验值不一致"):
        verify_backup(manifest)
