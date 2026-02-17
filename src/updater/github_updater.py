"""GitHub 自动更新模块 — 检查、下载和安装更新。

功能:
1. 检查 GitHub Releases 最新版本
2. 对比当前版本与最新版本
3. 下载更新包并进行 SHA256 校验
4. 提示用户安装更新
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None

logger = logging.getLogger(__name__)


# =====================================================================
# 数据结构
# =====================================================================

@dataclass
class UpdateInfo:
    """更新信息。"""
    version: str
    release_url: str
    download_url: str
    download_size: int
    release_notes: str
    published_at: str
    sha256: str | None = None
    
    @property
    def is_newer_than(self) -> Callable[[str], bool]:
        """返回一个比较版本的函数。"""
        return lambda current: compare_versions(self.version, current) > 0


def compare_versions(v1: str, v2: str) -> int:
    """比较两个版本号。
    
    Returns:
        1 如果 v1 > v2
        0 如果 v1 == v2
        -1 如果 v1 < v2
    """
    def normalize(v: str) -> list[int]:
        # 移除 'v' 前缀
        v = v.lstrip('v').lstrip('V')
        # 分割并转为数字列表
        parts = []
        for part in re.split(r'[.\-]', v):
            # 只保留数字部分
            match = re.match(r'(\d+)', part)
            if match:
                parts.append(int(match.group(1)))
        return parts
    
    parts1 = normalize(v1)
    parts2 = normalize(v2)
    
    # 补齐长度
    max_len = max(len(parts1), len(parts2))
    parts1.extend([0] * (max_len - len(parts1)))
    parts2.extend([0] * (max_len - len(parts2)))
    
    for a, b in zip(parts1, parts2):
        if a > b:
            return 1
        elif a < b:
            return -1
    return 0


# =====================================================================
# 更新器
# =====================================================================

class GitHubUpdater:
    """GitHub 更新器。"""
    
    # 默认 GitHub 仓库信息
    DEFAULT_OWNER = "wyg5208"  # WinClaw GitHub 组织/用户名
    DEFAULT_REPO = "WinClaw"    # WinClaw 仓库名
    
    # GitHub API 基础 URL
    API_BASE = "https://api.github.com"
    
    def __init__(
        self,
        owner: str | None = None,
        repo: str | None = None,
        current_version: str = "0.0.0",
    ):
        """初始化更新器。
        
        Args:
            owner: GitHub 用户名/组织名
            repo: 仓库名
            current_version: 当前版本号
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp 未安装,请运行: pip install aiohttp")
        
        self.owner = owner or self.DEFAULT_OWNER
        self.repo = repo or self.DEFAULT_REPO
        self.current_version = current_version
        self._session: aiohttp.ClientSession | None = None
    
    async def __aenter__(self) -> GitHubUpdater:
        """异步上下文管理器入口。"""
        self._session = aiohttp.ClientSession(
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": f"WinClaw/{self.current_version}",
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器退出。"""
        if self._session:
            await self._session.close()
            self._session = None
    
    async def check_update(self) -> UpdateInfo | None:
        """检查是否有新版本。
        
        Returns:
            更新信息,如果没有新版本则返回 None
        """
        if not self._session:
            raise RuntimeError("请在 async with 上下文中使用")
        
        try:
            url = f"{self.API_BASE}/repos/{self.owner}/{self.repo}/releases/latest"
            async with self._session.get(url) as response:
                if response.status == 404:
                    logger.info("没有找到发布版本")
                    return None
                
                if response.status != 200:
                    logger.error(f"GitHub API 错误: {response.status}")
                    return None
                
                data = await response.json()
                return self._parse_release(data)
        
        except aiohttp.ClientError as e:
            logger.error(f"网络错误: {e}")
            return None
        except Exception as e:
            logger.error(f"检查更新失败: {e}")
            return None
    
    async def get_all_releases(self, limit: int = 10) -> list[UpdateInfo]:
        """获取所有发布版本。
        
        Args:
            limit: 最多返回的版本数
            
        Returns:
            版本列表
        """
        if not self._session:
            raise RuntimeError("请在 async with 上下文中使用")
        
        releases = []
        try:
            url = f"{self.API_BASE}/repos/{self.owner}/{self.repo}/releases"
            params = {"per_page": limit}
            
            async with self._session.get(url, params=params) as response:
                if response.status != 200:
                    return releases
                
                data = await response.json()
                for release in data:
                    info = self._parse_release(release)
                    if info:
                        releases.append(info)
        
        except Exception as e:
            logger.error(f"获取版本列表失败: {e}")
        
        return releases
    
    def _parse_release(self, data: dict[str, Any]) -> UpdateInfo | None:
        """解析 GitHub Release 数据。"""
        try:
            tag_name = data.get("tag_name", "")
            version = tag_name.lstrip('v').lstrip('V')
            
            # 查找 Windows 安装包
            download_url = ""
            download_size = 0
            
            assets = data.get("assets", [])
            for asset in assets:
                name = asset.get("name", "").lower()
                # 优先选择 .exe 安装包
                if name.endswith(".exe") or name.endswith(".zip"):
                    download_url = asset.get("browser_download_url", "")
                    download_size = asset.get("size", 0)
                    break
            
            # 从 release body 中提取 SHA256
            sha256 = self._extract_sha256(data.get("body", ""))
            
            return UpdateInfo(
                version=version,
                release_url=data.get("html_url", ""),
                download_url=download_url,
                download_size=download_size,
                release_notes=data.get("body", ""),
                published_at=data.get("published_at", ""),
                sha256=sha256,
            )
        
        except Exception as e:
            logger.error(f"解析 Release 数据失败: {e}")
            return None
    
    def _extract_sha256(self, body: str) -> str | None:
        """从 release body 中提取 SHA256 校验和。"""
        if not body:
            return None
        
        # 常见格式: SHA256: xxxx 或 sha256sum: xxxx
        patterns = [
            r'SHA256[:\s]+([a-fA-F0-9]{64})',
            r'sha256[:\s]+([a-fA-F0-9]{64})',
            r'Checksum[:\s]+([a-fA-F0-9]{64})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                return match.group(1).lower()
        
        return None
    
    async def download_update(
        self,
        update_info: UpdateInfo,
        target_dir: Path | str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path | None:
        """下载更新包。
        
        Args:
            update_info: 更新信息
            target_dir: 目标目录,为 None 时使用临时目录
            progress_callback: 进度回调函数 (downloaded_bytes, total_bytes)
            
        Returns:
            下载的文件路径,失败返回 None
        """
        if not self._session:
            raise RuntimeError("请在 async with 上下文中使用")
        
        if not update_info.download_url:
            logger.error("没有可用的下载链接")
            return None
        
        # 确定目标路径
        if target_dir:
            target_dir = Path(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
        else:
            target_dir = Path(tempfile.mkdtemp(prefix="winclaw_update_"))
        
        # 从 URL 获取文件名
        filename = update_info.download_url.split("/")[-1]
        target_path = target_dir / filename
        
        try:
            async with self._session.get(update_info.download_url) as response:
                if response.status != 200:
                    logger.error(f"下载失败: HTTP {response.status}")
                    return None
                
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                
                with open(target_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback:
                            progress_callback(downloaded, total_size or update_info.download_size)
            
            logger.info(f"下载完成: {target_path}")
            return target_path
        
        except Exception as e:
            logger.error(f"下载失败: {e}")
            if target_path.exists():
                target_path.unlink()
            return None
    
    def verify_checksum(self, file_path: Path | str, expected_sha256: str) -> bool:
        """验证文件 SHA256 校验和。
        
        Args:
            file_path: 文件路径
            expected_sha256: 预期的 SHA256 值
            
        Returns:
            校验是否通过
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return False
        
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        
        actual = sha256_hash.hexdigest().lower()
        expected = expected_sha256.lower()
        
        if actual != expected:
            logger.error(f"SHA256 校验失败: 期望 {expected}, 实际 {actual}")
            return False
        
        logger.info("SHA256 校验通过")
        return True
    
    def has_update(self, update_info: UpdateInfo | None) -> bool:
        """判断是否有可用更新。
        
        Args:
            update_info: 更新信息
            
        Returns:
            是否有新版本
        """
        if not update_info:
            return False
        
        return compare_versions(update_info.version, self.current_version) > 0


# =====================================================================
# 版本信息
# =====================================================================

def get_current_version() -> str:
    """获取当前应用版本。"""
    try:
        # 尝试从 __init__.py 读取版本
        from src import __version__
        return __version__
    except (ImportError, AttributeError):
        pass
    
    try:
        # 尝试从 pyproject.toml 读取
        import tomllib
        pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
                return data.get("project", {}).get("version", "0.0.0")
    except Exception:
        pass
    
    return "0.0.0"


async def check_for_updates(
    owner: str | None = None,
    repo: str | None = None,
) -> UpdateInfo | None:
    """便捷函数：检查更新。
    
    Args:
        owner: GitHub 用户名/组织名
        repo: 仓库名
        
    Returns:
        更新信息,如果没有新版本返回 None
    """
    current = get_current_version()
    
    async with GitHubUpdater(owner, repo, current) as updater:
        update_info = await updater.check_update()
        
        if updater.has_update(update_info):
            return update_info
    
    return None
