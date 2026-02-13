#!/usr/bin/env python3
"""WinClaw 构建脚本。

功能:
1. 清理旧构建
2. 更新版本号
3. 运行 PyInstaller
4. 复制配置文件
5. 生成校验和
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"


def clean_build() -> None:
    """清理旧构建。"""
    print("==> 清理旧构建...")
    
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
        print(f"    已删除: {DIST_DIR}")
    
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
        print(f"    已删除: {BUILD_DIR}")
    
    # 清理 __pycache__
    for pycache in ROOT_DIR.rglob("__pycache__"):
        shutil.rmtree(pycache)
    
    print("    清理完成")


def get_version() -> str:
    """获取当前版本号。"""
    try:
        import tomllib
        pyproject = ROOT_DIR / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
            return data.get("project", {}).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def create_version_info(version: str) -> None:
    """创建版本信息文件（Windows 资源）。"""
    version_parts = version.split(".")
    while len(version_parts) < 4:
        version_parts.append("0")
    
    version_tuple = ", ".join(version_parts[:4])
    
    content = f'''# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({version_tuple}),
    prodvers=({version_tuple}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'WinClaw'),
        StringStruct('FileDescription', 'WinClaw - Windows AI Assistant'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'winclaw'),
        StringStruct('LegalCopyright', 'Copyright (c) {datetime.now().year} WinClaw'),
        StringStruct('OriginalFilename', 'winclaw.exe'),
        StringStruct('ProductName', 'WinClaw'),
        StringStruct('ProductVersion', '{version}')])
      ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'''
    
    version_file = ROOT_DIR / "file_version_info.txt"
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"    版本信息文件已创建: {version_file}")


def run_pyinstaller() -> bool:
    """运行 PyInstaller。"""
    print("==> 运行 PyInstaller...")
    
    spec_file = ROOT_DIR / "winclaw.spec"
    if not spec_file.exists():
        print(f"    错误: spec 文件不存在: {spec_file}")
        return False
    
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec_file)]
    
    try:
        result = subprocess.run(cmd, cwd=ROOT_DIR, check=True)
        print("    PyInstaller 完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"    PyInstaller 失败: {e}")
        return False


def copy_extra_files() -> None:
    """复制额外文件到输出目录。"""
    print("==> 复制额外文件...")
    
    output_dir = DIST_DIR / "WinClaw"
    if not output_dir.exists():
        print("    警告: 输出目录不存在")
        return
    
    # 复制配置文件
    config_src = ROOT_DIR / "config"
    config_dst = output_dir / "config"
    if config_src.exists() and not config_dst.exists():
        shutil.copytree(config_src, config_dst)
        print(f"    已复制: config/")
    
    # 复制资源文件
    resources_src = ROOT_DIR / "resources"
    resources_dst = output_dir / "resources"
    if resources_src.exists() and not resources_dst.exists():
        shutil.copytree(resources_src, resources_dst)
        print(f"    已复制: resources/")


def generate_checksum() -> str | None:
    """生成 SHA256 校验和。"""
    print("==> 生成校验和...")
    
    exe_path = DIST_DIR / "WinClaw" / "winclaw.exe"
    if not exe_path.exists():
        print(f"    警告: exe 文件不存在: {exe_path}")
        return None
    
    sha256_hash = hashlib.sha256()
    with open(exe_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    
    checksum = sha256_hash.hexdigest()
    
    # 保存到文件
    checksum_file = DIST_DIR / "WinClaw" / "winclaw.exe.sha256"
    with open(checksum_file, "w") as f:
        f.write(f"{checksum}  winclaw.exe\n")
    
    print(f"    SHA256: {checksum}")
    print(f"    已保存: {checksum_file}")
    
    return checksum


def create_zip() -> Path | None:
    """创建 ZIP 压缩包。"""
    print("==> 创建 ZIP 压缩包...")
    
    version = get_version()
    output_dir = DIST_DIR / "WinClaw"
    
    if not output_dir.exists():
        print("    警告: 输出目录不存在")
        return None
    
    zip_name = f"WinClaw-{version}-win64"
    zip_path = DIST_DIR / zip_name
    
    shutil.make_archive(str(zip_path), "zip", DIST_DIR, "WinClaw")
    
    final_path = DIST_DIR / f"{zip_name}.zip"
    print(f"    已创建: {final_path}")
    
    # 生成 ZIP 的校验和
    sha256_hash = hashlib.sha256()
    with open(final_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    
    checksum = sha256_hash.hexdigest()
    checksum_file = DIST_DIR / f"{zip_name}.zip.sha256"
    with open(checksum_file, "w") as f:
        f.write(f"{checksum}  {zip_name}.zip\n")
    
    print(f"    SHA256: {checksum}")
    
    return final_path


def main() -> int:
    """主函数。"""
    parser = argparse.ArgumentParser(description="WinClaw 构建脚本")
    parser.add_argument("--clean", action="store_true", help="仅清理构建")
    parser.add_argument("--no-clean", action="store_true", help="不清理旧构建")
    parser.add_argument("--no-zip", action="store_true", help="不创建 ZIP 压缩包")
    args = parser.parse_args()
    
    print("=" * 60)
    print("WinClaw 构建脚本")
    print("=" * 60)
    
    version = get_version()
    print(f"版本: {version}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 仅清理
    if args.clean:
        clean_build()
        return 0
    
    # 清理旧构建
    if not args.no_clean:
        clean_build()
    
    # 创建版本信息
    create_version_info(version)
    
    # 运行 PyInstaller
    if not run_pyinstaller():
        return 1
    
    # 复制额外文件
    copy_extra_files()
    
    # 生成校验和
    generate_checksum()
    
    # 创建 ZIP
    if not args.no_zip:
        create_zip()
    
    print()
    print("=" * 60)
    print("构建完成!")
    print(f"输出目录: {DIST_DIR / 'WinClaw'}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

