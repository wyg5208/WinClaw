"""Ollama 客户端 — 本地模型集成。

Phase 4.3 实现：
- 自动检测 Ollama 服务
- 获取已安装模型列表
- 模型拉取进度跟踪
- 零配置体验
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

# 默认 Ollama API 地址
DEFAULT_OLLAMA_URL = "http://localhost:11434"


@dataclass
class OllamaModel:
    """Ollama 模型信息。"""
    name: str
    size: str
    digest: str
    modified_at: str
    details: dict[str, Any] | None = None

    @property
    def display_name(self) -> str:
        """显示名称（去掉 tag 部分）。"""
        if ":" in self.name:
            return self.name.split(":")[0]
        return self.name


class OllamaClient:
    """Ollama REST API 客户端。"""

    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL, timeout: float = 30.0):
        """初始化客户端。

        Args:
            base_url: Ollama API 地址
            timeout: 请求超时时间
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._available: bool | None = None

    async def check_available(self) -> bool:
        """检查 Ollama 服务是否可用。"""
        if self._available is not None:
            return self._available

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                self._available = response.status_code == 200
                if self._available:
                    logger.info("Ollama 服务可用: %s", self._base_url)
                return self._available
        except Exception as e:
            logger.debug("Ollama 服务不可用: %s", e)
            self._available = False
            return False

    async def list_models(self) -> list[OllamaModel]:
        """获取已安装的模型列表。"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
                data = response.json()

                models = []
                for item in data.get("models", []):
                    models.append(OllamaModel(
                        name=item.get("name", "unknown"),
                        size=self._format_size(item.get("size", 0)),
                        digest=item.get("digest", ""),
                        modified_at=item.get("modified_at", ""),
                        details=item.get("details"),
                    ))
                logger.info("Ollama 已安装 %d 个模型", len(models))
                return models
        except Exception as e:
            logger.error("获取 Ollama 模型列表失败: %s", e)
            return []

    async def pull_model(
        self,
        model_name: str,
        progress_callback: Callable[[str, int], None] | None = None,
    ) -> bool:
        """拉取模型。

        Args:
            model_name: 模型名称（如 llama3.2）
            progress_callback: 进度回调函数 (status, percentage)

        Returns:
            是否成功
        """
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/pull",
                    json={"name": model_name, "stream": True},
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            import json
                            data = json.loads(line)
                            status = data.get("status", "")
                            completed = data.get("completed", 0)
                            total = data.get("total", 0)

                            if total > 0:
                                percentage = int(completed / total * 100)
                            else:
                                percentage = 0

                            if progress_callback:
                                progress_callback(status, percentage)

                            logger.debug("Pull model %s: %s (%d%%)", model_name, status, percentage)

                            if status == "success":
                                logger.info("模型 %s 拉取成功", model_name)
                                return True

                        except json.JSONDecodeError:
                            continue

            return False
        except Exception as e:
            logger.error("拉取模型 %s 失败: %s", model_name, e)
            return False

    async def get_model_info(self, model_name: str) -> dict[str, Any] | None:
        """获取模型详情。"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/show",
                    json={"name": model_name},
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("获取模型 %s 详情失败: %s", model_name, e)
            return None

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        stream: bool = False,
    ) -> Any:
        """与模型对话。

        Args:
            model: 模型名称
            messages: 消息列表
            stream: 是否流式输出

        Returns:
            响应内容或异步迭代器
        """
        if stream:
            return self._chat_stream(model, messages)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")

    async def _chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
    ):
        """流式对话。"""
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        import json
                        data = json.loads(line)
                        message = data.get("message", {})
                        if message.get("content"):
                            yield message["content"]
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小。"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    @property
    def is_available(self) -> bool | None:
        """返回上次检查的可用状态。"""
        return self._available


# 全局单例
_ollama_client: OllamaClient | None = None


def get_ollama_client(base_url: str = DEFAULT_OLLAMA_URL) -> OllamaClient:
    """获取 Ollama 客户端单例。"""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient(base_url)
    return _ollama_client
