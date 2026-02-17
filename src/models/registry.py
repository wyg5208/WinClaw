"""模型注册中心 — 管理所有可用 AI 模型的配置与调用。

Phase 1 重构：
- 接入 AppConfig 配置系统（也兼容直接传入 TOML 路径）
- 增加 tags 字段 + 按 Provider / tags 查询
- 字段校验（必填字段检查）
- UsageRecord 独立为 cost 模块引用的数据类

Phase 4 增强：
- 网络错误自动重试（指数退避）
"""

from __future__ import annotations

import asyncio
import logging
import os
import tomllib
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import litellm

# 降低 LiteLLM 的日志噪音
litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# 默认配置文件路径（兼容不使用 AppConfig 的场景）
_DEFAULT_MODELS_TOML = Path(__file__).resolve().parent.parent.parent / "config" / "models.toml"

# ModelConfig 必填字段
_REQUIRED_FIELDS = {"id", "name", "provider", "api_type"}


@dataclass
class ModelConfig:
    """单个模型的配置信息。"""

    key: str  # 配置文件中的键名，如 "deepseek-chat"
    id: str  # 模型 ID，传给 LiteLLM 的标识
    name: str  # 显示名称
    provider: str  # 提供商：openai / anthropic / deepseek / google / ollama
    api_type: str  # API 类型
    base_url: str = ""  # 自定义 API 基地址
    api_key_env: str = ""  # API Key 环境变量名
    input_types: list[str] = field(default_factory=lambda: ["text"])
    supports_function_calling: bool = True
    context_window: int = 128000
    max_tokens: int = 8192
    cost_input: float = 0.0  # 每百万 token 输入费用 (USD)
    cost_output: float = 0.0  # 每百万 token 输出费用 (USD)
    tags: list[str] = field(default_factory=list)

    @property
    def supports_image(self) -> bool:
        return "image" in self.input_types

    @property
    def is_local(self) -> bool:
        return self.provider == "ollama" or "local" in self.tags

    @property
    def is_free(self) -> bool:
        return self.cost_input == 0.0 and self.cost_output == 0.0

    @property
    def is_available(self) -> bool:
        """检查模型是否可用（API Key是否已配置）。"""
        import os
        # 本地模型（Ollama）总是可用的
        if self.is_local:
            return True
        # 如果没有配置API Key环境变量，认为是可用的（可能是自定义API）
        if not self.api_key_env:
            return True
        # 检查环境变量是否已配置
        return bool(os.environ.get(self.api_key_env))


@dataclass
class UsageRecord:
    """单次调用的 token 用量记录。"""

    model_key: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


class ModelRegistry:
    """模型注册中心。负责加载配置、选择模型、调用模型、记录用量。"""

    def __init__(self, config_path: Path | None = None, models_data: dict | None = None):
        """初始化模型注册中心。

        Args:
            config_path: 模型配置 TOML 文件路径（不传则用默认路径）
            models_data: 直接传入已解析的模型配置字典（优先于 config_path）
        """
        self._models: dict[str, ModelConfig] = {}
        self._usage_history: list[UsageRecord] = []

        if models_data is not None:
            self._load_from_dict(models_data)
        else:
            config_path = config_path or _DEFAULT_MODELS_TOML
            if config_path.exists():
                self._load_from_toml(config_path)
            else:
                logger.warning("模型配置文件不存在: %s，使用空配置", config_path)

        # 自动检测并注册本地 Ollama 模型
        self._detect_and_register_ollama_models()

    # ------------------------------------------------------------------
    # Ollama 自动检测
    # ------------------------------------------------------------------

    def _detect_and_register_ollama_models(self) -> None:
        """自动检测本地 Ollama 服务并注册已安装的模型。"""
        try:
            import httpx
        except ImportError:
            logger.debug("httpx 未安装，跳过 Ollama 检测")
            return

        ollama_url = "http://localhost:11434"

        # 检查 Ollama 服务是否可用
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{ollama_url}/api/tags")
                if response.status_code != 200:
                    logger.debug("Ollama 服务不可用，状态码: %s", response.status_code)
                    return
        except Exception:
            logger.debug("Ollama 服务未运行，跳过检测")
            return

        # 获取已安装的模型列表
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(f"{ollama_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                ollama_models = data.get("models", [])
        except Exception as e:
            logger.warning("获取 Ollama 模型列表失败: %s", e)
            return

        if not ollama_models:
            logger.debug("Ollama 服务运行中但未安装任何模型")
            return

        # 注册检测到的模型
        registered_count = 0
        for item in ollama_models:
            model_name = item.get("name", "unknown")
            base_name = model_name.split(':')[0]
            
            # 检查是否已经存在相同ID的模型（避免重复注册）
            # 检查方式1: 完全匹配的 ollama/model_name
            model_id = f"ollama/{model_name}"
            exists = any(m.id == model_id or m.id == model_name for m in self._models.values())
            
            # 检查方式2: 检查基础名称是否已存在（如 gemma3）
            if not exists:
                exists = any(base_name in m.id for m in self._models.values() if m.provider == "ollama")
            
            if exists:
                logger.debug("模型 %s 已存在，跳过注册", model_name)
                continue

            # 自动注册模型
            self.register_ollama_model(model_name)
            registered_count += 1
            logger.info("自动注册 Ollama 模型: %s", model_name)

        if registered_count > 0:
            logger.info("共自动注册了 %d 个 Ollama 模型", registered_count)

    # ------------------------------------------------------------------
    # 配置加载
    # ------------------------------------------------------------------

    def _load_from_toml(self, path: Path) -> None:
        """从 TOML 文件加载模型配置。"""
        with open(path, "rb") as f:
            data = tomllib.load(f)
        models_section = data.get("models", {})
        self._load_from_dict(models_section)

    def _load_from_dict(self, models_dict: dict[str, dict]) -> None:
        """从字典加载模型配置，带字段校验。"""
        for key, cfg in models_dict.items():
            # 校验必填字段
            missing = _REQUIRED_FIELDS - set(cfg.keys())
            if missing:
                logger.warning("模型 %s 缺少必填字段 %s，已跳过", key, missing)
                continue

            self._models[key] = ModelConfig(
                key=key,
                id=cfg["id"],
                name=cfg["name"],
                provider=cfg["provider"],
                api_type=cfg["api_type"],
                base_url=cfg.get("base_url", ""),
                api_key_env=cfg.get("api_key_env", ""),
                input_types=cfg.get("input_types", ["text"]),
                supports_function_calling=cfg.get("supports_function_calling", True),
                context_window=cfg.get("context_window", 128000),
                max_tokens=cfg.get("max_tokens", 8192),
                cost_input=cfg.get("cost_input", 0.0),
                cost_output=cfg.get("cost_output", 0.0),
                tags=cfg.get("tags", []),
            )
        logger.info("已加载 %d 个模型配置", len(self._models))

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, key: str) -> ModelConfig | None:
        """按键名获取模型。"""
        return self._models.get(key)

    def list_models(self) -> list[ModelConfig]:
        """列出所有模型。"""
        return list(self._models.values())

    def list_available_models(self) -> list[ModelConfig]:
        """列出所有可用的模型（已配置API Key或本地模型）。"""
        return [m for m in self._models.values() if m.is_available]

    def find_by_capability(
        self,
        *,
        needs_function_calling: bool = False,
        needs_image: bool = False,
    ) -> list[ModelConfig]:
        """按能力筛选模型。"""
        results = []
        for m in self._models.values():
            if needs_function_calling and not m.supports_function_calling:
                continue
            if needs_image and not m.supports_image:
                continue
            results.append(m)
        return results

    def find_by_provider(self, provider: str) -> list[ModelConfig]:
        """按提供商筛选模型。"""
        return [m for m in self._models.values() if m.provider == provider]

    def find_by_tag(self, tag: str) -> list[ModelConfig]:
        """按标签筛选模型。"""
        return [m for m in self._models.values() if tag in m.tags]

    def find_local_models(self) -> list[ModelConfig]:
        """获取所有本地模型。"""
        return [m for m in self._models.values() if m.is_local]

    def find_free_models(self) -> list[ModelConfig]:
        """获取所有免费模型。"""
        return [m for m in self._models.values() if m.is_free]

    # ------------------------------------------------------------------
    # Ollama 集成（Phase 4.3）
    # ------------------------------------------------------------------

    async def refresh_ollama_models(self) -> list[ModelConfig]:
        """检测 Ollama 并自动注册已安装的模型。

        Returns:
            新注册的 Ollama 模型列表
        """
        from src.models.ollama import get_ollama_client

        client = get_ollama_client()
        if not await client.check_available():
            logger.debug("Ollama 服务不可用，跳过模型注册")
            return []

        ollama_models = await client.list_models()
        new_models = []

        for model in ollama_models:
            # 检查是否已注册
            key = f"ollama_{model.display_name}"
            if key in self._models:
                continue

            # 创建模型配置
            config = ModelConfig(
                key=key,
                id=f"ollama/{model.name}",  # LiteLLM 格式
                name=f"{model.display_name} (Ollama)",
                provider="ollama",
                api_type="ollama",
                base_url="http://localhost:11434",
                api_key_env="",  # Ollama 不需要 API Key
                tags=["local", "ollama"],
                cost_input=0.0,
                cost_output=0.0,
            )
            self._models[key] = config
            new_models.append(config)
            logger.info("注册 Ollama 模型: %s", model.name)

        return new_models

    def register_ollama_model(self, model_name: str, **kwargs: Any) -> ModelConfig:
        """手动注册单个 Ollama 模型。

        Args:
            model_name: Ollama 模型名称（如 llama3.2）
            **kwargs: 额外配置参数

        Returns:
            注册的模型配置
        """
        key = f"ollama_{model_name.split(':')[0]}"
        display_name = model_name.split(":")[0]

        config = ModelConfig(
            key=key,
            id=f"ollama/{model_name}",
            name=kwargs.get("name", f"{display_name} (Ollama)"),
            provider="ollama",
            api_type="ollama",
            base_url=kwargs.get("base_url", "http://localhost:11434"),
            api_key_env="",
            input_types=kwargs.get("input_types", ["text"]),
            supports_function_calling=kwargs.get("supports_function_calling", True),
            context_window=kwargs.get("context_window", 128000),
            max_tokens=kwargs.get("max_tokens", 8192),
            tags=["local", "ollama"],
            cost_input=0.0,
            cost_output=0.0,
        )
        self._models[key] = config
        logger.info("手动注册 Ollama 模型: %s", model_name)
        return config

    # ------------------------------------------------------------------
    # 调用
    # ------------------------------------------------------------------

    # 网络重试配置
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # 指数退避（秒）

    async def chat(
        self,
        model_key: str,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        event_bus: Any = None,  # 可选的 EventBus 用于发布重试事件
        **kwargs: Any,
    ) -> dict[str, Any]:
        """通过 LiteLLM 调用指定模型（带重试）。

        Args:
            model_key: 模型键名
            messages: 消息列表
            tools: 工具 schema 列表
            event_bus: 可选的 EventBus，用于发布网络重试事件
            **kwargs: 其他参数

        Returns:
            LiteLLM / OpenAI 兼容的 response 对象。
        """
        model_cfg = self._models.get(model_key)
        if model_cfg is None:
            raise ValueError(f"未知模型: {model_key}")

        call_kwargs: dict[str, Any] = {
            "model": model_cfg.id,
            "messages": messages,
            "max_tokens": model_cfg.max_tokens,
        }

        # 自定义 API 基地址（DeepSeek 等 OpenAI 兼容服务）
        if model_cfg.base_url:
            # Ollama 使用 api_base 参数
            call_kwargs["api_base"] = model_cfg.base_url

        # 自定义 API Key 环境变量
        if model_cfg.api_key_env:
            api_key = os.environ.get(model_cfg.api_key_env)
            if api_key:
                call_kwargs["api_key"] = api_key
            else:
                raise ValueError(
                    f"模型 {model_key} 需要环境变量 {model_cfg.api_key_env}，"
                    f"请设置: $env:{model_cfg.api_key_env} = 'your-api-key'"
                )

        if tools and model_cfg.supports_function_calling:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"
        call_kwargs.update(kwargs)

        # 带重试的调用
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug("调用模型 %s (id=%s, attempt=%d)", model_key, model_cfg.id, attempt + 1)
                response = await litellm.acompletion(**call_kwargs)

                # 记录用量
                usage = getattr(response, "usage", None)
                if usage:
                    record = UsageRecord(
                        model_key=model_key,
                        prompt_tokens=getattr(usage, "prompt_tokens", 0),
                        completion_tokens=getattr(usage, "completion_tokens", 0),
                        total_tokens=getattr(usage, "total_tokens", 0),
                    )
                    # 计算成本（每百万 token）
                    record.cost = (
                        record.prompt_tokens * model_cfg.cost_input
                        + record.completion_tokens * model_cfg.cost_output
                    ) / 1_000_000
                    self._usage_history.append(record)

                return response

            except Exception as e:
                last_error = e
                error_name = type(e).__name__
                
                # 判断是否为可重试的网络错误
                is_network_error = any(
                    pattern in error_name 
                    for pattern in ["Connection", "Timeout", "Network", "ConnectError", "TimeoutException"]
                )
                
                if is_network_error and attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        "模型调用网络错误 (attempt %d/%d): %s, %d秒后重试...",
                        attempt + 1, self.MAX_RETRIES, error_name, delay
                    )
                    
                    # 发布重试事件
                    if event_bus:
                        try:
                            await event_bus.emit("network_retry", {
                                "attempt": attempt + 1,
                                "max_attempts": self.MAX_RETRIES,
                                "delay": delay,
                                "error": error_name,
                            })
                        except Exception:
                            pass
                    
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    # 非网络错误或已达到最大重试次数，抛出异常
                    raise

        # 理论上不会到达这里，但作为保险
        raise last_error

    async def chat_stream(
        self,
        model_key: str,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        event_bus: Any = None,  # 可选的 EventBus 用于发布重试事件
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        """通过 LiteLLM 流式调用指定模型（带初始连接重试）。

        与 chat() 参数一致，但使用 stream=True 返回异步生成器。
        每个 chunk 的结构: chunk.choices[0].delta 包含 .content 或 .tool_calls。
        
        注意：重试只在初始连接阶段进行，一旦开始流式传输则不再重试。

        Args:
            model_key: 模型键名
            messages: 消息列表
            tools: 工具 schema 列表
            event_bus: 可选的 EventBus，用于发布网络重试事件
            **kwargs: 其他参数

        Returns:
            异步生成器，逐 chunk 产出 LiteLLM 流式响应片段。
        """
        model_cfg = self._models.get(model_key)
        if model_cfg is None:
            raise ValueError(f"未知模型: {model_key}")

        call_kwargs: dict[str, Any] = {
            "model": model_cfg.id,
            "messages": messages,
            "max_tokens": model_cfg.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        # 自定义 API 基地址
        if model_cfg.base_url:
            # 所有模型统一使用 api_base 参数
            call_kwargs["api_base"] = model_cfg.base_url

        # 自定义 API Key
        if model_cfg.api_key_env:
            api_key = os.environ.get(model_cfg.api_key_env)
            if api_key:
                call_kwargs["api_key"] = api_key
            else:
                raise ValueError(
                    f"模型 {model_key} 需要环境变量 {model_cfg.api_key_env}，"
                    f"请设置: $env:{model_cfg.api_key_env} = 'your-api-key'"
                )

        if tools and model_cfg.supports_function_calling:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"
        call_kwargs.update(kwargs)

        # 带重试的初始连接
        response = None
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug("流式调用模型 %s (id=%s, attempt=%d)", model_key, model_cfg.id, attempt + 1)
                response = await litellm.acompletion(**call_kwargs)
                break  # 成功获取响应，跳出重试循环
            except Exception as e:
                last_error = e
                error_name = type(e).__name__
                
                # 判断是否为可重试的网络错误
                is_network_error = any(
                    pattern in error_name 
                    for pattern in ["Connection", "Timeout", "Network", "ConnectError", "TimeoutException"]
                )
                
                if is_network_error and attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        "流式调用网络错误 (attempt %d/%d): %s, %d秒后重试...",
                        attempt + 1, self.MAX_RETRIES, error_name, delay
                    )
                    
                    # 发布重试事件
                    if event_bus:
                        try:
                            await event_bus.emit("network_retry", {
                                "attempt": attempt + 1,
                                "max_attempts": self.MAX_RETRIES,
                                "delay": delay,
                                "error": error_name,
                            })
                        except Exception:
                            pass
                    
                    await asyncio.sleep(delay)
                else:
                    raise

        if response is None:
            raise last_error

        async for chunk in response:
            yield chunk

    def record_stream_usage(self, model_key: str, usage: Any) -> None:
        """记录流式调用的 token 用量（从最后一个 chunk 的 usage 中提取）。

        Args:
            model_key: 模型键名
            usage: 流式响应最后一个 chunk 中的 usage 对象
        """
        model_cfg = self._models.get(model_key)
        if not model_cfg or not usage:
            return
        record = UsageRecord(
            model_key=model_key,
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
            total_tokens=getattr(usage, "total_tokens", 0),
        )
        record.cost = (
            record.prompt_tokens * model_cfg.cost_input
            + record.completion_tokens * model_cfg.cost_output
        ) / 1_000_000
        self._usage_history.append(record)

    # ------------------------------------------------------------------
    # 用量统计
    # ------------------------------------------------------------------

    @property
    def usage_history(self) -> list[UsageRecord]:
        """返回完整用量历史。"""
        return list(self._usage_history)

    @property
    def total_cost(self) -> float:
        return sum(r.cost for r in self._usage_history)

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self._usage_history)

    def get_usage_summary(self) -> dict[str, Any]:
        return {
            "total_calls": len(self._usage_history),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost, 6),
            "history": self._usage_history,
        }

    def add_usage(self, record: UsageRecord) -> None:
        """手动添加用量记录（供 CostTracker 使用）。"""
        self._usage_history.append(record)

    def clear_usage(self) -> None:
        """清空用量历史。"""
        self._usage_history.clear()
