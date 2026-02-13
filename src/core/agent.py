"""Agent 核心循环 — ReAct 模式的 AI 智能体（Phase 1 重构版）。

重构变更：
- 接入 EventBus，推理全流程发布事件
- 使用 SessionManager 管理对话历史
- 使用 ModelSelector 选择模型
- 使用 CostTracker 记录费用
- Phase 4: 增加推理超时控制
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from src.core.event_bus import EventBus
from src.core.events import (
    AgentResponseEvent,
    AgentThinkingEvent,
    ErrorEvent,
    EventType,
    FileGeneratedEvent,
    ModelCallEvent,
    ModelResponseEvent,
    ModelUsageEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from src.core.session import SessionManager
from src.models.cost import CostTracker
from src.models.registry import ModelRegistry, UsageRecord
from src.models.selector import ModelSelector
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# 默认推理超时时间（秒）
DEFAULT_INFERENCE_TIMEOUT = 120

# 流式响应单 chunk 超时（秒）
STREAM_CHUNK_TIMEOUT = 60


async def _stream_with_timeout(
    stream: AsyncGenerator[Any, None],
    timeout: float,
):
    """带超时的异步生成器包装器。

    如果在指定时间内没有收到下一个 chunk，则抛出 TimeoutError。
    """
    while True:
        try:
            chunk = await asyncio.wait_for(stream.__anext__(), timeout=timeout)
            yield chunk
        except StopAsyncIteration:
            break

# 默认 system prompt
DEFAULT_SYSTEM_PROMPT = """你是 WinClaw，一个运行在 Windows 上的 AI 桌面智能体。
你可以通过工具来帮助用户完成各种任务，包括执行命令、读写文件、截屏等。

当你需要完成某个任务时，请选择合适的工具来执行。
如果任务不需要使用工具，请直接回答用户的问题。

重要规则：
- 执行命令时优先使用 PowerShell 语法
- 文件路径使用 Windows 风格（反斜杠或正斜杠均可）
- 操作完成后向用户清晰说明结果
- 如果工具执行出错，尝试其他方法或告知用户
- 请用中文回复用户

工具选择优先级：
当存在功能重叠的工具时，按以下优先级选择：
1. 内置工具（shell/file/screen/browser/search 等）- 优先使用，响应更快、稳定性更高
2. MCP 扩展工具（mcp_filesystem/mcp_fetch 等）- 仅在内置工具无法完成时使用

具体场景：
- 读写本地文件：使用 file.read / file.write（内置）
- 搜索网页：使用 search.web_search（内置）
- 截图操作：使用 screen.capture（内置）
- 浏览器自动化：使用 browser.*（内置）
- MCP 工具适用于：内置工具不支持的特殊格式、需要第三方服务集成的场景

附件处理指引：
当用户提供附件文件时，会在消息开头看到 [附件信息] 区块。根据文件类型和用户请求选择处理方式：
- 图片文件 (.png/.jpg/.jpeg 等)：可使用 ocr.recognize_file 识别文字
- 文本文件 (.txt/.md/.csv/.json 等)：可使用 file.read 读取内容
- 代码文件 (.py/.js/.java 等)：可使用 file.read 读取代码
- 根据用户的具体指令选择合适的处理方式
- 如用户未明确指定处理方式，可以询问用户想要如何处理"""


@dataclass
class AgentResponse:
    """Agent 单次交互的完整响应。"""

    content: str = ""
    tool_calls_count: int = 0
    total_tokens: int = 0
    steps: list[AgentStep] = field(default_factory=list)


@dataclass
class AgentStep:
    """Agent 推理的单个步骤。"""

    step_type: str  # "tool_call" | "tool_result" | "response"
    tool_name: str = ""
    tool_action: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: str = ""
    content: str = ""


class Agent:
    """AI 智能体核心。执行 ReAct 循环。

    Phase 1 架构：
    - EventBus: 每步推理发布事件
    - SessionManager: 管理对话历史和上下文截断
    - ModelSelector: 智能选择模型
    - CostTracker: 记录费用
    
    Phase 4 增强：
    - 推理超时控制
    """

    def __init__(
        self,
        model_registry: ModelRegistry,
        tool_registry: ToolRegistry,
        event_bus: EventBus | None = None,
        session_manager: SessionManager | None = None,
        model_selector: ModelSelector | None = None,
        cost_tracker: CostTracker | None = None,
        model_key: str = "deepseek-chat",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_steps: int = 30,
        inference_timeout: float = DEFAULT_INFERENCE_TIMEOUT,
    ):
        self.model_registry = model_registry
        self.tool_registry = tool_registry
        self.event_bus = event_bus or EventBus()
        # 初始化会话管理器，带有持久化存储
        if session_manager is None:
            from src.core.storage import ChatStorage
            storage = ChatStorage()
            self.session_manager = SessionManager(
                system_prompt=system_prompt,
                storage=storage,
            )
        else:
            self.session_manager = session_manager
        self.model_selector = model_selector or ModelSelector(
            model_registry, default_model=model_key,
        )
        self.cost_tracker = cost_tracker or CostTracker()
        self.model_key = model_key
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.inference_timeout = inference_timeout

    # 兼容旧接口
    @property
    def messages(self) -> list[dict[str, Any]]:
        """兼容旧接口：返回当前会话的消息列表。"""
        return self.session_manager.current_session.messages

    def reset(self) -> None:
        """清空当前会话的对话历史。"""
        self.session_manager.clear_messages()

    # ------------------------------------------------------------------
    # 文件生成检测
    # ------------------------------------------------------------------

    # 会触发文件生成事件的 (tool_name, action_name) 集合
    _FILE_GEN_ACTIONS: set[tuple[str, str]] = {
        ("file", "write"),
        ("file", "edit"),
        ("screen", "screenshot"),
        ("screen", "capture"),
    }

    async def _check_and_emit_file_generated(
        self,
        tool_name: str,
        action_name: str,
        result,
        session_id: str,
    ) -> None:
        """检查工具执行结果是否产生了文件，如果是则发出 FILE_GENERATED 事件。"""
        if not result.is_success:
            return

        file_path = result.data.get("path", "") if result.data else ""
        if not file_path:
            return

        # 只对写入/创建类操作发出事件
        from pathlib import Path as _P
        p = _P(file_path)
        if not p.exists() or not p.is_file():
            return

        # 判断是否为文件写入类动作
        is_file_gen = (tool_name, action_name) in self._FILE_GEN_ACTIONS
        # 对于未明确列出的动作，如果 result.data 中有 path 且文件存在，也视为文件生成
        if not is_file_gen and action_name in ("write", "save", "create", "export", "download"):
            is_file_gen = True

        if is_file_gen:
            await self.event_bus.emit(
                EventType.FILE_GENERATED,
                FileGeneratedEvent(
                    file_path=file_path,
                    file_name=p.name,
                    source_tool=tool_name,
                    source_action=action_name,
                    file_size=p.stat().st_size,
                    session_id=session_id,
                ),
            )

    async def chat(self, user_input: str) -> AgentResponse:
        """处理用户输入，执行 ReAct 循环，返回最终回复。

        Args:
            user_input: 用户的输入文本

        Returns:
            AgentResponse 包含最终回复、步骤详情、token 用量
        """
        response = AgentResponse()
        session = self.session_manager.current_session
        session_id = session.id

        # 添加用户消息
        self.session_manager.add_message(role="user", content=user_input)

        # 发布用户输入事件
        await self.event_bus.emit(EventType.USER_INPUT, {
            "text": user_input,
            "session_id": session_id,
        })

        # 获取工具 schema
        tools = self.tool_registry.get_all_schemas()

        # 选择模型
        model_cfg = self.model_selector.select_for_task(
            needs_function_calling=bool(tools),
            model_key=self.model_key,
        )

        # ReAct 循环
        for step_idx in range(self.max_steps):
            # 发布思考事件
            await self.event_bus.emit(EventType.AGENT_THINKING, AgentThinkingEvent(
                step=step_idx + 1,
                max_steps=self.max_steps,
                model_key=model_cfg.key,
                session_id=session_id,
            ))

            # 获取截断后的消息
            messages = self.session_manager.get_messages(
                max_tokens=model_cfg.context_window,
            )

            # 发布模型调用事件
            await self.event_bus.emit(EventType.MODEL_CALL, ModelCallEvent(
                model_key=model_cfg.key,
                model_id=model_cfg.id,
                message_count=len(messages),
                has_tools=bool(tools),
                session_id=session_id,
            ))

            # 调用模型（带超时）
            try:
                model_response = await asyncio.wait_for(
                    self.model_registry.chat(
                        model_key=model_cfg.key,
                        messages=messages,
                        tools=tools if tools else None,
                    ),
                    timeout=self.inference_timeout,
                )
            except asyncio.TimeoutError:
                logger.error("模型调用超时 (%s秒)", self.inference_timeout)
                await self.event_bus.emit(EventType.MODEL_ERROR, ErrorEvent(
                    source="model",
                    message=f"模型调用超时 ({self.inference_timeout}秒)",
                    error_type="TimeoutError",
                    session_id=session_id,
                ))
                response.content = f"抱歉，AI 模型响应超时，请稍后重试或简化您的问题。"
                return response
            except Exception as e:
                logger.error("模型调用失败: %s", e)
                await self.event_bus.emit(EventType.MODEL_ERROR, ErrorEvent(
                    source="model",
                    message=str(e),
                    error_type=type(e).__name__,
                    session_id=session_id,
                ))
                response.content = f"抱歉，AI 模型调用失败: {e}"
                return response

            # 解析模型响应
            choice = model_response.choices[0]
            message = choice.message

            # 记录 token 用量
            usage = getattr(model_response, "usage", None)
            if usage:
                tokens = getattr(usage, "total_tokens", 0)
                response.total_tokens += tokens
                self.session_manager.update_tokens(tokens)

                # 记录费用
                usage_record = UsageRecord(
                    model_key=model_cfg.key,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0),
                    completion_tokens=getattr(usage, "completion_tokens", 0),
                    total_tokens=tokens,
                    cost=(
                        getattr(usage, "prompt_tokens", 0) * model_cfg.cost_input
                        + getattr(usage, "completion_tokens", 0) * model_cfg.cost_output
                    ) / 1_000_000,
                )
                self.cost_tracker.record(usage_record, session_id=session_id)

                await self.event_bus.emit(EventType.MODEL_USAGE, ModelUsageEvent(
                    model_key=model_cfg.key,
                    prompt_tokens=usage_record.prompt_tokens,
                    completion_tokens=usage_record.completion_tokens,
                    total_tokens=tokens,
                    cost=usage_record.cost,
                    session_id=session_id,
                ))

            # 发布模型响应事件
            tool_calls = getattr(message, "tool_calls", None)
            content = getattr(message, "content", "") or ""

            await self.event_bus.emit(EventType.MODEL_RESPONSE, ModelResponseEvent(
                model_key=model_cfg.key,
                has_tool_calls=bool(tool_calls),
                content_preview=content[:100],
                session_id=session_id,
            ))

            if not tool_calls:
                # 模型给出了最终回复
                response.content = content
                response.steps.append(AgentStep(
                    step_type="response",
                    content=content,
                ))
                self.session_manager.add_assistant_message(content)

                await self.event_bus.emit(EventType.AGENT_RESPONSE, AgentResponseEvent(
                    content=content,
                    total_steps=step_idx + 1,
                    total_tokens=response.total_tokens,
                    tool_calls_count=response.tool_calls_count,
                    session_id=session_id,
                ))

                logger.info("Agent 最终回复（%d 步，%d tokens）", step_idx + 1, response.total_tokens)
                return response

            # 有 tool calls，需要执行工具
            assistant_msg_tool_calls = []
            for tc in tool_calls:
                func_name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                assistant_msg_tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": func_name,
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                })

            self.session_manager.add_assistant_message(
                content=content,
                tool_calls=assistant_msg_tool_calls,
            )

            # 逐个执行 tool calls
            for tc in tool_calls:
                func_name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                response.tool_calls_count += 1

                resolved = self.tool_registry.resolve_function_name(func_name)
                tool_name = resolved[0] if resolved else func_name
                action_name = resolved[1] if resolved else ""

                # 发布工具调用事件
                await self.event_bus.emit(EventType.TOOL_CALL, ToolCallEvent(
                    tool_name=tool_name,
                    action_name=action_name,
                    arguments=arguments,
                    function_name=func_name,
                    session_id=session_id,
                ))

                step = AgentStep(
                    step_type="tool_call",
                    tool_name=tool_name,
                    tool_action=action_name,
                    tool_args=arguments,
                )

                # 执行工具
                result = await self.tool_registry.call_function(func_name, arguments)
                step.tool_result = result.to_message()
                response.steps.append(step)

                # 发布工具结果事件
                await self.event_bus.emit(EventType.TOOL_RESULT, ToolResultEvent(
                    tool_name=tool_name,
                    action_name=action_name,
                    status=result.status.value,
                    output=result.output[:500] if result.output else "",
                    error=result.error,
                    duration_ms=result.duration_ms,
                    session_id=session_id,
                ))

                logger.info(
                    "  工具 %s.%s → %s (%.0fms)",
                    tool_name, action_name,
                    result.status.value, result.duration_ms,
                )

                # 检测文件生成
                await self._check_and_emit_file_generated(
                    tool_name, action_name, result, session_id,
                )

                # 将工具结果加入对话历史
                tool_result_content = result.to_message()
                if result.is_success and result.data and result.data.get("base64"):
                    tool_result_content = result.output

                self.session_manager.add_tool_message(
                    tool_call_id=tc.id,
                    content=tool_result_content,
                )

        # 超过最大步数
        response.content = "（任务执行步数已达上限，请尝试拆分为更小的任务）"
        self.session_manager.add_assistant_message(response.content)

        await self.event_bus.emit(EventType.AGENT_ERROR, ErrorEvent(
            source="agent",
            message="达到最大步数限制",
            session_id=session_id,
        ))

        return response

    async def chat_stream(self, user_input: str) -> AsyncGenerator[str, None]:
        """流式处理用户输入，yield 文本片段。

        与 chat() 使用相同的 ReAct 循环逻辑，但对最终文本回复进行流式输出：
        - 工具调用步骤：内部收集完整 tool_calls 后执行，不 yield
        - 文本回复：逐 chunk yield 给调用方
        - 工具调用信息通过 EventBus 事件传递

        Args:
            user_input: 用户的输入文本

        Yields:
            str: 模型生成的文本片段
        """
        session = self.session_manager.current_session
        session_id = session.id
        total_tokens = 0
        tool_calls_count = 0

        # 添加用户消息
        self.session_manager.add_message(role="user", content=user_input)

        # 发布用户输入事件
        await self.event_bus.emit(EventType.USER_INPUT, {
            "text": user_input,
            "session_id": session_id,
        })

        # 获取工具 schema
        tools = self.tool_registry.get_all_schemas()

        # 选择模型
        model_cfg = self.model_selector.select_for_task(
            needs_function_calling=bool(tools),
            model_key=self.model_key,
        )

        # ReAct 循环
        for step_idx in range(self.max_steps):
            # 发布思考事件
            await self.event_bus.emit(EventType.AGENT_THINKING, AgentThinkingEvent(
                step=step_idx + 1,
                max_steps=self.max_steps,
                model_key=model_cfg.key,
                session_id=session_id,
            ))

            # 获取截断后的消息
            messages = self.session_manager.get_messages(
                max_tokens=model_cfg.context_window,
            )

            # 发布模型调用事件
            await self.event_bus.emit(EventType.MODEL_CALL, ModelCallEvent(
                model_key=model_cfg.key,
                model_id=model_cfg.id,
                message_count=len(messages),
                has_tools=bool(tools),
                session_id=session_id,
            ))

            # 流式调用模型（带超时）
            try:
                collected_content = ""
                collected_tool_calls: list[dict] = []
                last_usage = None

                # 使用超时包装器处理流
                stream = self.model_registry.chat_stream(
                    model_key=model_cfg.key,
                    messages=messages,
                    tools=tools if tools else None,
                )
                
                async for chunk in _stream_with_timeout(stream, STREAM_CHUNK_TIMEOUT):
                    choice = chunk.choices[0] if chunk.choices else None
                    if choice is None:
                        # 可能是最后一个 chunk 只含 usage
                        usage = getattr(chunk, "usage", None)
                        if usage:
                            last_usage = usage
                        continue

                    delta = choice.delta

                    # 收集文本内容
                    delta_content = getattr(delta, "content", None) or ""
                    if delta_content:
                        collected_content += delta_content
                        yield delta_content  # 实时 yield 文本片段

                    # 收集 tool_calls（增量拼接）
                    delta_tool_calls = getattr(delta, "tool_calls", None)
                    if delta_tool_calls:
                        for dtc in delta_tool_calls:
                            idx = dtc.index
                            # 扩展列表
                            while len(collected_tool_calls) <= idx:
                                collected_tool_calls.append({
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                })
                            tc_entry = collected_tool_calls[idx]
                            if dtc.id:
                                tc_entry["id"] = dtc.id
                            if dtc.function:
                                if dtc.function.name:
                                    tc_entry["function"]["name"] += dtc.function.name
                                if dtc.function.arguments:
                                    tc_entry["function"]["arguments"] += dtc.function.arguments

                    # 从 chunk 提取 usage（部分 provider 在最后一个 chunk 附带）
                    usage = getattr(chunk, "usage", None)
                    if usage:
                        last_usage = usage

                # 记录 token 用量
                if last_usage:
                    tokens = getattr(last_usage, "total_tokens", 0)
                    total_tokens += tokens
                    self.session_manager.update_tokens(tokens)
                    self.model_registry.record_stream_usage(model_cfg.key, last_usage)

                    usage_record = UsageRecord(
                        model_key=model_cfg.key,
                        prompt_tokens=getattr(last_usage, "prompt_tokens", 0),
                        completion_tokens=getattr(last_usage, "completion_tokens", 0),
                        total_tokens=tokens,
                        cost=(
                            getattr(last_usage, "prompt_tokens", 0) * model_cfg.cost_input
                            + getattr(last_usage, "completion_tokens", 0) * model_cfg.cost_output
                        ) / 1_000_000,
                    )
                    self.cost_tracker.record(usage_record, session_id=session_id)

                    await self.event_bus.emit(EventType.MODEL_USAGE, ModelUsageEvent(
                        model_key=model_cfg.key,
                        prompt_tokens=usage_record.prompt_tokens,
                        completion_tokens=usage_record.completion_tokens,
                        total_tokens=tokens,
                        cost=usage_record.cost,
                        session_id=session_id,
                    ))

                # 发布模型响应事件
                has_tool_calls = bool(collected_tool_calls)
                await self.event_bus.emit(EventType.MODEL_RESPONSE, ModelResponseEvent(
                    model_key=model_cfg.key,
                    has_tool_calls=has_tool_calls,
                    content_preview=collected_content[:100],
                    session_id=session_id,
                ))

                if not has_tool_calls:
                    # 最终回复（文本已通过 yield 流式输出）
                    self.session_manager.add_assistant_message(collected_content)

                    await self.event_bus.emit(EventType.AGENT_RESPONSE, AgentResponseEvent(
                        content=collected_content,
                        total_steps=step_idx + 1,
                        total_tokens=total_tokens,
                        tool_calls_count=tool_calls_count,
                        session_id=session_id,
                    ))

                    logger.info(
                        "Agent 流式回复（%d 步，%d tokens）",
                        step_idx + 1, total_tokens,
                    )
                    return

                # 有 tool calls，执行工具
                assistant_msg_tool_calls = []
                for tc_entry in collected_tool_calls:
                    assistant_msg_tool_calls.append({
                        "id": tc_entry["id"],
                        "type": "function",
                        "function": {
                            "name": tc_entry["function"]["name"],
                            "arguments": tc_entry["function"]["arguments"],
                        },
                    })

                self.session_manager.add_assistant_message(
                    content=collected_content,
                    tool_calls=assistant_msg_tool_calls,
                )

                # 逐个执行 tool calls
                for tc_entry in collected_tool_calls:
                    func_name = tc_entry["function"]["name"]
                    try:
                        arguments = json.loads(tc_entry["function"]["arguments"])
                    except json.JSONDecodeError:
                        arguments = {}

                    tool_calls_count += 1

                    resolved = self.tool_registry.resolve_function_name(func_name)
                    tool_name = resolved[0] if resolved else func_name
                    action_name = resolved[1] if resolved else ""

                    # 发布工具调用事件
                    await self.event_bus.emit(EventType.TOOL_CALL, ToolCallEvent(
                        tool_name=tool_name,
                        action_name=action_name,
                        arguments=arguments,
                        function_name=func_name,
                        session_id=session_id,
                    ))

                    # 执行工具
                    result = await self.tool_registry.call_function(func_name, arguments)

                    # 发布工具结果事件
                    await self.event_bus.emit(EventType.TOOL_RESULT, ToolResultEvent(
                        tool_name=tool_name,
                        action_name=action_name,
                        status=result.status.value,
                        output=result.output[:500] if result.output else "",
                        error=result.error,
                        duration_ms=result.duration_ms,
                        session_id=session_id,
                    ))

                    logger.info(
                        "  工具 %s.%s → %s (%.0fms)",
                        tool_name, action_name,
                        result.status.value, result.duration_ms,
                    )

                    # 检测文件生成
                    await self._check_and_emit_file_generated(
                        tool_name, action_name, result, session_id,
                    )

                    # 将工具结果加入对话历史
                    tool_result_content = result.to_message()
                    if result.is_success and result.data and result.data.get("base64"):
                        tool_result_content = result.output

                    self.session_manager.add_tool_message(
                        tool_call_id=tc_entry["id"],
                        content=tool_result_content,
                    )

            except asyncio.TimeoutError:
                logger.error("流式模型响应超时")
                await self.event_bus.emit(EventType.MODEL_ERROR, ErrorEvent(
                    source="model",
                    message=f"流式响应超时 ({STREAM_CHUNK_TIMEOUT}秒无响应)",
                    error_type="TimeoutError",
                    session_id=session_id,
                ))
                yield "\n抱歉，AI 模型响应超时，请稍后重试。"
                return
            except Exception as e:
                logger.error("流式模型调用失败: %s", e)
                await self.event_bus.emit(EventType.MODEL_ERROR, ErrorEvent(
                    source="model",
                    message=str(e),
                    error_type=type(e).__name__,
                    session_id=session_id,
                ))
                yield f"\n抱歉，AI 模型调用失败: {e}"
                return

        # 超过最大步数
        max_step_msg = "（任务执行步数已达上限，请尝试拆分为更小的任务）"
        self.session_manager.add_assistant_message(max_step_msg)

        await self.event_bus.emit(EventType.AGENT_ERROR, ErrorEvent(
            source="agent",
            message="达到最大步数限制",
            session_id=session_id,
        ))

        yield max_step_msg
