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
    ModelReasoningEvent,
    ModelResponseEvent,
    ModelUsageEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from src.core.prompts import (
    build_system_prompt,
    build_system_prompt_from_intent,
    detect_intent_with_confidence,
    DEFAULT_SYSTEM_PROMPT,
    CORE_SYSTEM_PROMPT,
    IntentResult,
)
from src.core.tool_exposure import ToolExposureEngine
from src.core.session import SessionManager
from src.core.task_trace import TaskTraceCollector, create_trace_collector
from src.models.cost import CostTracker
from src.models.registry import ModelRegistry, UsageRecord
from src.models.selector import ModelSelector
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# 默认推理超时时间（秒）
DEFAULT_INFERENCE_TIMEOUT = 120

# 流式响应单 chunk 超时（秒）
STREAM_CHUNK_TIMEOUT = 60

# 连续失败阈值
MAX_CONSECUTIVE_FAILURES = 3

# 单次工具调用数量上限（防止模型同时调用过多不相关工具）
MAX_TOOLS_PER_CALL = 3


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

    Phase 6 增强：
    - 渐进式工具暴露（ToolExposureEngine）
    - 单次工具调用数量限制
    - 增强意图识别与置信度评估
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
        system_prompt: str = CORE_SYSTEM_PROMPT,
        max_steps: int = 60,
        inference_timeout: float = DEFAULT_INFERENCE_TIMEOUT,
        # Phase 6: 工具暴露策略配置
        enable_tool_tiering: bool = True,
        enable_schema_annotation: bool = True,
        failures_to_upgrade: int = 2,
        # Phase 6: 全链路追踪配置
        enable_trace: bool = True,
        trace_config: dict[str, Any] | None = None,
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

        # Phase 6: 工具暴露策略引擎
        self.tool_exposure = ToolExposureEngine(
            tool_registry,
            enabled=enable_tool_tiering,
            enable_annotation=enable_schema_annotation,
            failures_to_upgrade=failures_to_upgrade,
        )

        # Phase 6: 全链路追踪配置
        self._enable_trace = enable_trace
        self._trace_config = trace_config or {}

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

        # Phase 6: 创建全链路追踪采集器
        trace_config = self._trace_config.copy()
        trace_config["enabled"] = self._enable_trace
        trace_collector = create_trace_collector(
            session_id=session_id,
            user_input=user_input,
            config=trace_config,
        )

        # 添加用户消息
        self.session_manager.add_message(role="user", content=user_input)

        # 发布用户输入事件
        await self.event_bus.emit(EventType.USER_INPUT, {
            "text": user_input,
            "session_id": session_id,
        })

        # Phase 6: 增强意图识别 + 渐进式工具暴露
        intent_result = detect_intent_with_confidence(user_input)
        self.tool_exposure.reset()  # 新对话重置暴露策略状态

        # 获取工具 schema（通过暴露引擎分层过滤 + 标注）
        tools = self.tool_exposure.get_schemas(intent_result)

        # Phase 6: 记录意图识别和工具暴露
        exposed_tool_names = [s["function"]["name"].split("_")[0] for s in tools]
        trace_collector.set_intent(
            intent_result,
            tier=self.tool_exposure.current_tier,
            exposed_tools=exposed_tool_names,
        )

        logger.info(
            "意图识别: primary=%s, confidence=%.2f, intents=%s, tier=%s, schemas=%d",
            intent_result.primary_intent, intent_result.confidence,
            intent_result.intents, self.tool_exposure.current_tier, len(tools),
        )

        # 选择模型
        model_cfg = self.model_selector.select_for_task(
            needs_function_calling=bool(tools),
            model_key=self.model_key,
        )

        # 动态构建 System Prompt（使用增强版意图结果）
        dynamic_system_prompt = build_system_prompt_from_intent(intent_result)
        self.session_manager.update_system_prompt(dynamic_system_prompt)

        # 连续失败计数器
        consecutive_failures = 0

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

            # 任务锚定机制：从第 3 步开始，每 3 步锚定一次（Phase 6 增强：含执行状态摘要）
            if step_idx >= 3 and step_idx % 3 == 0:
                anchor_message = {
                    "role": "user",
                    "content": (
                        f"[执行状态] 原始请求：{user_input}\n"
                        f"已完成 {step_idx} 步，工具调用 {response.tool_calls_count} 次，"
                        f"连续失败 {consecutive_failures} 次\n"
                        f"请继续推进此任务，不要执行无关操作。"
                    ),
                }
                messages = messages + [anchor_message]

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
                trace_collector.finalize(status="error", tokens=response.total_tokens, response_preview=response.content)
                trace_collector.flush()
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
                trace_collector.finalize(status="error", tokens=response.total_tokens, response_preview=response.content)
                trace_collector.flush()
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
                trace_collector.finalize(
                    status="completed",
                    tokens=response.total_tokens,
                    response_preview=response.content,
                )
                trace_collector.flush()
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

            # 单次工具调用数量限制
            if len(tool_calls) > MAX_TOOLS_PER_CALL:
                logger.warning(
                    "单次工具调用数量(%d)超过上限(%d)，拒绝执行",
                    len(tool_calls), MAX_TOOLS_PER_CALL,
                )
                reject_msg = (
                    f"[系统] 单次工具调用数量({len(tool_calls)})超过限制({MAX_TOOLS_PER_CALL})，"
                    f"请分步执行，每步最多调用 {MAX_TOOLS_PER_CALL} 个工具。"
                )
                self.session_manager.add_assistant_message(
                    content=content,
                    tool_calls=assistant_msg_tool_calls,
                )
                # 为每个 tool_call 都添加拒绝消息（API 要求每个 tool_call 必须有对应 tool 消息）
                for tc in tool_calls:
                    self.session_manager.add_tool_message(
                        tool_call_id=tc.id,
                        content=reject_msg,
                    )
                continue

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

                # Phase 6: 检查工具是否已废弃
                tool_cfg = self.tool_registry.get_tool_config(tool_name)
                if tool_cfg.get("deprecated", False):
                    deprecation_msg = tool_cfg.get("deprecation_message", "此工具已废弃")
                    migrate_to = tool_cfg.get("migrate_to", "")
                    logger.warning(
                        "调用已废弃工具: %s (替代: %s)",
                        tool_name, migrate_to or "无",
                    )
                    # 返回废弃提示消息
                    result_msg = f"[已废弃] {deprecation_msg}"
                    if migrate_to:
                        result_msg += f"\n请使用 {migrate_to} 替代。"
                    self.session_manager.add_tool_message(
                        tool_call_id=tc.id,
                        content=result_msg,
                    )
                    continue

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
                step.tool_result = result.to_message(failure_count=consecutive_failures)
                response.steps.append(step)

                # Phase 6: 记录工具调用到追踪
                trace_collector.add_tool_call(
                    step=step_idx + 1,
                    function_name=func_name,
                    arguments=arguments,
                    status=result.status.value,
                    duration_ms=result.duration_ms,
                    error=result.error,
                    output=result.output,
                )

                # 连续失败检测
                if result.status.value != "success":
                    consecutive_failures += 1
                    upgrade_info = self.tool_exposure.report_failure()
                    # Phase 6: 记录层级升级
                    if upgrade_info:
                        trace_collector.add_tier_upgrade(upgrade_info[0], upgrade_info[1])
                    logger.warning(
                        "工具调用失败 (%d/%d): %s.%s",
                        consecutive_failures, MAX_CONSECUTIVE_FAILURES,
                        tool_name, action_name
                    )
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        error_msg = (
                            f"抱歉，连续 {consecutive_failures} 次工具调用失败，任务终止。\n"
                            f"请检查：\n"
                            f"1. 相关服务是否正常运行\n"
                            f"2. 参数是否正确\n"
                            f"3. 网络连接是否稳定"
                        )
                        response.content = error_msg
                        self.session_manager.add_assistant_message(error_msg)
                        await self.event_bus.emit(EventType.AGENT_ERROR, ErrorEvent(
                            source="agent",
                            message=f"连续 {consecutive_failures} 次工具调用失败",
                            session_id=session_id,
                        ))
                        # Phase 6: 完成追踪并写入
                        trace_collector.finalize(
                            status="error",
                            tokens=response.total_tokens,
                            response_preview=error_msg,
                        )
                        trace_collector.flush()
                        return response
                else:
                    consecutive_failures = 0  # 成功则重置计数器
                    self.tool_exposure.report_success()

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
                tool_result_content = result.to_message(failure_count=consecutive_failures)
                # 如果有 html_image，添加到内容中（用于 GUI 直接显示图片）
                if result.is_success and result.data:
                    html_img = result.data.get("html_image")
                    if html_img:
                        tool_result_content = f"{result.output}\n\n{html_img}"

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

        trace_collector.finalize(
            status="max_steps",
            tokens=response.total_tokens,
            response_preview=response.content,
        )
        trace_collector.flush()

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

        # Phase 6: 创建全链路追踪采集器
        trace_config = self._trace_config.copy()
        trace_config["enabled"] = self._enable_trace
        trace_collector = create_trace_collector(
            session_id=session_id,
            user_input=user_input,
            config=trace_config,
        )

        # 添加用户消息
        self.session_manager.add_message(role="user", content=user_input)

        # 发布用户输入事件
        await self.event_bus.emit(EventType.USER_INPUT, {
            "text": user_input,
            "session_id": session_id,
        })

        # Phase 6: 增强意图识别 + 渐进式工具暴露
        intent_result = detect_intent_with_confidence(user_input)
        self.tool_exposure.reset()

        # 获取工具 schema（通过暴露引擎分层过滤 + 标注）
        tools = self.tool_exposure.get_schemas(intent_result)

        # Phase 6: 记录意图识别和工具暴露
        exposed_tool_names = [s["function"]["name"].split("_")[0] for s in tools]
        trace_collector.set_intent(
            intent_result,
            tier=self.tool_exposure.current_tier,
            exposed_tools=exposed_tool_names,
        )

        logger.info(
            "流式模式意图识别: primary=%s, confidence=%.2f, intents=%s, tier=%s, schemas=%d",
            intent_result.primary_intent, intent_result.confidence,
            intent_result.intents, self.tool_exposure.current_tier, len(tools),
        )

        # 选择模型
        model_cfg = self.model_selector.select_for_task(
            needs_function_calling=bool(tools),
            model_key=self.model_key,
        )

        # 动态构建 System Prompt（使用增强版意图结果）
        dynamic_system_prompt = build_system_prompt_from_intent(intent_result)
        self.session_manager.update_system_prompt(dynamic_system_prompt)

        # 连续失败计数器
        consecutive_failures = 0

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

            # 任务锚定机制：从第 3 步开始，每 3 步锚定一次（Phase 6 增强：含执行状态摘要）
            if step_idx >= 3 and step_idx % 3 == 0:
                anchor_message = {
                    "role": "user",
                    "content": (
                        f"[执行状态] 原始请求：{user_input}\n"
                        f"已完成 {step_idx} 步，工具调用 {tool_calls_count} 次，"
                        f"连续失败 {consecutive_failures} 次\n"
                        f"请继续推进此任务，不要执行无关操作。"
                    ),
                }
                messages = messages + [anchor_message]

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
                # 本地Ollama模型可能需要更长时间，使用更长的超时
                chunk_timeout = STREAM_CHUNK_TIMEOUT
                if model_cfg.provider == "ollama":
                    chunk_timeout = 300  # Ollama本地模型5分钟超时
                
                stream = self.model_registry.chat_stream(
                    model_key=model_cfg.key,
                    messages=messages,
                    tools=tools if tools else None,
                )
                
                async for chunk in _stream_with_timeout(stream, chunk_timeout):
                    choice = chunk.choices[0] if chunk.choices else None
                    if choice is None:
                        # 可能是最后一个 chunk 只含 usage
                        usage = getattr(chunk, "usage", None)
                        if usage:
                            last_usage = usage
                        continue

                    delta = choice.delta

                    # 收集思考过程 (reasoning_content) - DeepSeek等模型支持
                    delta_reasoning = getattr(delta, "reasoning_content", None) or ""
                    if delta_reasoning:
                        await self.event_bus.emit(EventType.MODEL_REASONING, ModelReasoningEvent(
                            reasoning=delta_reasoning,
                            is_delta=True,
                            is_complete=False,
                            session_id=session_id,
                        ))

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

                # 发送思考过程完成事件
                await self.event_bus.emit(EventType.MODEL_REASONING, ModelReasoningEvent(
                    reasoning="",
                    is_delta=False,
                    is_complete=True,
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
                    trace_collector.finalize(
                        status="completed",
                        tokens=total_tokens,
                        response_preview=collected_content,
                    )
                    trace_collector.flush()
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

                # 单次工具调用数量限制
                if len(collected_tool_calls) > MAX_TOOLS_PER_CALL:
                    logger.warning(
                        "流式模式: 单次工具调用数量(%d)超过上限(%d)，拒绝执行",
                        len(collected_tool_calls), MAX_TOOLS_PER_CALL,
                    )
                    reject_msg = (
                        f"[系统] 单次工具调用数量({len(collected_tool_calls)})超过限制({MAX_TOOLS_PER_CALL})，"
                        f"请分步执行，每步最多调用 {MAX_TOOLS_PER_CALL} 个工具。"
                    )
                    self.session_manager.add_assistant_message(
                        content=collected_content,
                        tool_calls=assistant_msg_tool_calls,
                    )
                    for tc_entry in collected_tool_calls:
                        self.session_manager.add_tool_message(
                            tool_call_id=tc_entry["id"],
                            content=reject_msg,
                        )
                    continue

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

                    # Phase 6: 检查工具是否已废弃
                    tool_cfg = self.tool_registry.get_tool_config(tool_name)
                    if tool_cfg.get("deprecated", False):
                        deprecation_msg = tool_cfg.get("deprecation_message", "此工具已废弃")
                        migrate_to = tool_cfg.get("migrate_to", "")
                        logger.warning(
                            "调用已废弃工具: %s (替代: %s)",
                            tool_name, migrate_to or "无",
                        )
                        # 返回废弃提示消息
                        result_msg = f"[已废弃] {deprecation_msg}"
                        if migrate_to:
                            result_msg += f"\n请使用 {migrate_to} 替代。"
                        self.session_manager.add_tool_message(
                            tool_call_id=tc_entry["id"],
                            content=result_msg,
                        )
                        continue

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

                    # Phase 6: 记录工具调用到追踪
                    trace_collector.add_tool_call(
                        step=step_idx + 1,
                        function_name=func_name,
                        arguments=arguments,
                        status=result.status.value,
                        duration_ms=result.duration_ms,
                        error=result.error,
                        output=result.output,
                    )

                    # 获取 html_image 用于 GUI 显示（不发送到 AI）
                    html_image = ""
                    if result.is_success and result.data:
                        html_image = result.data.get("html_image", "")

                    # 发布工具结果事件（包含 html_image 用于 GUI 显示）
                    await self.event_bus.emit(EventType.TOOL_RESULT, ToolResultEvent(
                        tool_name=tool_name,
                        action_name=action_name,
                        status=result.status.value,
                        output=result.output[:500] if result.output else "",
                        error=result.error,
                        duration_ms=result.duration_ms,
                        session_id=session_id,
                        html_image=html_image,
                    ))

                    logger.info(
                        "  工具 %s.%s → %s (%.0fms)",
                        tool_name, action_name,
                        result.status.value, result.duration_ms,
                    )

                    # 连续失败检测
                    if result.status.value != "success":
                        consecutive_failures += 1
                        upgrade_info = self.tool_exposure.report_failure()
                        # Phase 6: 记录层级升级
                        if upgrade_info:
                            trace_collector.add_tier_upgrade(upgrade_info[0], upgrade_info[1])
                        logger.warning(
                            "工具调用失败 (%d/%d): %s.%s",
                            consecutive_failures, MAX_CONSECUTIVE_FAILURES,
                            tool_name, action_name
                        )
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            error_msg = (
                                f"\n抱歉，连续 {consecutive_failures} 次工具调用失败，任务终止。\n"
                                f"请检查相关服务是否正常运行。"
                            )
                            self.session_manager.add_assistant_message(error_msg)
                            await self.event_bus.emit(EventType.AGENT_ERROR, ErrorEvent(
                                source="agent",
                                message=f"连续 {consecutive_failures} 次工具调用失败",
                                session_id=session_id,
                            ))
                            trace_collector.finalize(
                                status="error",
                                tokens=total_tokens,
                                response_preview=error_msg,
                            )
                            trace_collector.flush()
                            yield error_msg
                            return
                    else:
                        consecutive_failures = 0  # 成功则重置计数器
                        self.tool_exposure.report_success()

                    # 检测文件生成
                    await self._check_and_emit_file_generated(
                        tool_name, action_name, result, session_id,
                    )

                    # 将工具结果加入对话历史
                    tool_result_content = result.to_message(failure_count=consecutive_failures)
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
                error_msg = "\n抱歉，AI 模型响应超时，请稍后重试。"
                trace_collector.finalize(status="error", tokens=total_tokens, response_preview=error_msg)
                trace_collector.flush()
                yield error_msg
                return
            except Exception as e:
                logger.error("流式模型调用失败: %s", e)
                await self.event_bus.emit(EventType.MODEL_ERROR, ErrorEvent(
                    source="model",
                    message=str(e),
                    error_type=type(e).__name__,
                    session_id=session_id,
                ))
                error_msg = f"\n抱歉，AI 模型调用失败: {e}"
                trace_collector.finalize(status="error", tokens=total_tokens, response_preview=error_msg)
                trace_collector.flush()
                yield error_msg
                return

        # 超过最大步数
        max_step_msg = "（任务执行步数已达上限，请尝试拆分为更小的任务）"
        self.session_manager.add_assistant_message(max_step_msg)

        await self.event_bus.emit(EventType.AGENT_ERROR, ErrorEvent(
            source="agent",
            message="达到最大步数限制",
            session_id=session_id,
        ))

        trace_collector.finalize(status="max_steps", tokens=total_tokens, response_preview=max_step_msg)
        trace_collector.flush()

        yield max_step_msg
