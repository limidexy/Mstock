"""仅在本地备份数据并核验完整性，不联网、不上传、不自动解压覆盖。"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


用途 = {"raw": "数据源原始响应，可重新获取但应保留研究证据",
        "processed": "股票池和下载覆盖范围", "cache": "离线行情与指标输入",
        "review": "人工校对记录，必须保留，不可由程序重建",
        "output": "历史候选、诊断报告与离线图表", "manual": "用户关注票与私人备注"}


def file_hash(path: Path) -> str:
    """流式计算文件校验值。"""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def create_backup(project: Path, output: Path) -> Path:
    """建立独立数据压缩包和逐文件清单，已有备份不得覆盖。"""
    project, output = project.resolve(), output.resolve()
    data = project / "data"
    if not data.is_dir():
        raise ValueError("备份失败：项目数据目录不存在。")
    if output.is_relative_to(data):
        raise ValueError("备份失败：输出目录不能位于数据目录内部。")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "Mstock_本地数据.zip"
    manifest = output / "数据迁移清单.json"
    if archive.exists() or manifest.exists():
        raise ValueError("备份失败：目标已有备份，请选择新的空目录，禁止覆盖。")
    records = []
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(data.rglob("*")):
            if path.is_symlink():
                raise ValueError("备份失败：数据中存在符号链接，请先人工检查。")
            if not path.is_file() or path.name == ".gitkeep":
                continue
            relative = path.relative_to(project).as_posix()
            checksum = file_hash(path)
            bundle.write(path, relative)
            records.append({"相对路径": relative, "字节数": path.stat().st_size,
                            "SHA256": checksum, "用途": 用途.get(Path(relative).parts[1], "本地数据")})
    result = {"生成时间": datetime.now().astimezone().isoformat(), "源项目路径": str(project),
              "压缩包": archive.name, "压缩包SHA256": file_hash(archive), "文件数量": len(records),
              "未压缩总字节数": sum(row["字节数"] for row in records),
              "说明": "仅供独立私下迁移；不包含代码、虚拟环境和项目根目录真实凭据；不得提交GitHub。",
              "文件": records}
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    verify_backup(manifest)
    return manifest


def verify_backup(manifest: Path) -> int:
    """核验压缩包及其每个条目，不执行解压。"""
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    archive_name = metadata["压缩包"]
    if Path(archive_name).name != archive_name:
        raise ValueError("校验失败：压缩包文件名不安全。")
    archive = manifest.parent / archive_name
    if file_hash(archive) != metadata["压缩包SHA256"]:
        raise ValueError("校验失败：压缩包校验值不一致。")
    rows = metadata["文件"]
    expected = {row["相对路径"] for row in rows}
    if len(expected) != len(rows) or len(rows) != metadata["文件数量"]:
        raise ValueError("校验失败：清单条目重复或数量不一致。")
    with zipfile.ZipFile(archive) as bundle:
        if set(bundle.namelist()) != expected or len(bundle.namelist()) != len(rows):
            raise ValueError("校验失败：压缩包与清单文件集合不同。")
        for row in rows:
            name = row["相对路径"]
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != "data" or ".." in parts or "\\" in name or ":" in name:
                raise ValueError("校验失败：数据路径不安全。")
            with bundle.open(name) as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != row["SHA256"] or bundle.getinfo(name).file_size != row["字节数"]:
                raise ValueError(f"校验失败：文件内容不一致：{name}")
    return len(rows)


def main() -> int:
    """解析中文迁移命令并输出中文结果。"""
    parser = argparse.ArgumentParser(description="生成或核验本地数据迁移备份，不联网、不上传。")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-dir", type=Path, help="新建备份目录，已有备份不会覆盖。")
    mode.add_argument("--verify", type=Path, help="核验已有数据迁移清单。")
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1], help="项目根目录。")
    args = parser.parse_args()
    try:
        if args.verify:
            print(f"数据备份校验通过，文件数量：{verify_backup(args.verify)}")
        else:
            manifest = create_backup(args.project, args.output_dir)
            print(f"数据备份和逐文件校验已完成：{manifest}")
        return 0
    except Exception as exc:
        print(f"迁移备份失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
