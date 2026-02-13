"""工作流引擎 — 支持多步骤任务编排、参数传递、条件分支、失败重试/回滚。

功能特性：
1. 支持 YAML/JSON 格式定义工作流
2. 步骤间参数传递（支持 Jinja2 模板语法）
3. 条件分支（基于前序步骤结果）
4. 失败重试与回滚机制
5. 进度追踪与事件发布
6. 嵌套工作流支持

工作流定义示例（YAML）：
```yaml
name: "截屏分析工作流"
description: "截屏并分析内容，根据结果采取不同动作"
version: "1.0"
steps:
  - id: "step_1"
    name: "截取全屏"
    tool: "screen"
    action: "capture_full"
    args:
      quality: 85
    retry: 2
    
  - id: "step_2"
    name: "分析截图内容"
    tool: "ai_analyze"
    action: "vision"
    args:
      image: "{{ steps.step_1.result.image_path }}"
      prompt: "这张图片上有什么内容？"
    
  - id: "step_3"
    name: "根据分析结果决策"
    condition: "{{ 'error' in steps.step_2.result.text.lower() }}"
    tool: "notify"
    action: "send"
    args:
      title: "发现错误"
      message: "{{ steps.step_2.result.text }}"
```
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Template

from src.core.event_bus import EventBus
from src.core.events import EventType
from src.tools.base import ToolResult, ToolResultStatus
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# =====================================================================
# 枚举与常量
# =====================================================================

class WorkflowStatus(str, Enum):
    """工作流状态枚举。"""
    PENDING = "pending"           # 未开始
    RUNNING = "running"           # 执行中
    PAUSED = "paused"             # 已暂停
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    CANCELLED = "cancelled"       # 已取消


class StepStatus(str, Enum):
    """步骤状态枚举。"""
    PENDING = "pending"           # 未执行
    RUNNING = "running"           # 执行中
    COMPLETED = "completed"       # 成功完成
    FAILED = "failed"             # 失败
    SKIPPED = "skipped"           # 跳过（条件不满足）
    RETRYING = "retrying"         # 重试中


# =====================================================================
# 数据类
# =====================================================================

@dataclass
class WorkflowStep:
    """工作流步骤定义。"""
    id: str                                # 步骤唯一标识
    name: str                              # 步骤名称
    tool: str                              # 工具名
    action: str                            # 动作名
    args: dict[str, Any] = field(default_factory=dict)  # 参数（支持模板）
    condition: str = ""                    # 执行条件（Jinja2 表达式）
    retry: int = 0                         # 重试次数
    retry_delay: float = 1.0               # 重试间隔（秒）
    timeout: float = 0                     # 超时时间（秒，0 表示无限制）
    on_failure: str = "abort"              # 失败处理：abort(中止)/continue(继续)/retry(重试)
    rollback_action: str = ""              # 回滚动作（可选）
    
    # 运行时状态
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str = ""
    start_time: float = 0
    end_time: float = 0
    attempt_count: int = 0


@dataclass
class WorkflowDefinition:
    """工作流定义。"""
    name: str                              # 工作流名称
    description: str = ""                  # 描述
    version: str = "1.0"                   # 版本号
    steps: list[WorkflowStep] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)  # 全局变量
    timeout: float = 0                     # 整体超时（秒）
    on_failure: str = "rollback"           # 失败策略：rollback/abort/continue


@dataclass
class WorkflowContext:
    """工作流执行上下文。"""
    workflow_id: str                       # 工作流实例 ID
    definition: WorkflowDefinition         # 工作流定义
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_step_index: int = 0
    variables: dict[str, Any] = field(default_factory=dict)  # 动态变量
    step_results: dict[str, Any] = field(default_factory=dict)  # 步骤结果缓存
    start_time: float = 0
    end_time: float = 0
    error: str = ""
    
    def get_elapsed_time(self) -> float:
        """获取已执行时间（秒）。"""
        if self.start_time == 0:
            return 0
        end = self.end_time if self.end_time > 0 else time.time()
        return end - self.start_time


# =====================================================================
# 工作流引擎
# =====================================================================

class WorkflowEngine:
    """工作流引擎核心。
    
    职责：
    - 加载工作流定义（YAML/JSON/dict）
    - 执行工作流步骤
    - 参数渲染（Jinja2 模板）
    - 条件判断
    - 失败重试与回滚
    - 进度事件发布
    """
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        event_bus: EventBus | None = None,
    ):
        self.tool_registry = tool_registry
        self.event_bus = event_bus or EventBus()
        
        # 工作流实例缓存（workflow_id -> WorkflowContext）
        self._contexts: dict[str, WorkflowContext] = {}
    
    # ----------------------------------------------------------------
    # 工作流加载
    # ----------------------------------------------------------------
    
    def load_from_file(self, file_path: str | Path) -> WorkflowDefinition:
        """从文件加载工作流定义。
        
        Args:
            file_path: YAML/JSON 文件路径
            
        Returns:
            WorkflowDefinition
        """
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")
        
        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)
        elif path.suffix == ".json":
            data = json.loads(content)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")
        
        return self.load_from_dict(data)
    
    def load_from_dict(self, data: dict[str, Any]) -> WorkflowDefinition:
        """从字典加载工作流定义。"""
        steps = []
        for step_data in data.get("steps", []):
            step = WorkflowStep(
                id=step_data["id"],
                name=step_data["name"],
                tool=step_data["tool"],
                action=step_data["action"],
                args=step_data.get("args", {}),
                condition=step_data.get("condition", ""),
                retry=step_data.get("retry", 0),
                retry_delay=step_data.get("retry_delay", 1.0),
                timeout=step_data.get("timeout", 0),
                on_failure=step_data.get("on_failure", "abort"),
                rollback_action=step_data.get("rollback_action", ""),
            )
            steps.append(step)
        
        return WorkflowDefinition(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            steps=steps,
            variables=data.get("variables", {}),
            timeout=data.get("timeout", 0),
            on_failure=data.get("on_failure", "rollback"),
        )
    
    # ----------------------------------------------------------------
    # 工作流执行
    # ----------------------------------------------------------------
    
    async def execute(
        self,
        workflow: WorkflowDefinition,
        workflow_id: str | None = None,
        initial_vars: dict[str, Any] | None = None,
    ) -> WorkflowContext:
        """执行工作流。
        
        Args:
            workflow: 工作流定义
            workflow_id: 工作流实例 ID（可选，默认生成）
            initial_vars: 初始变量（可选）
            
        Returns:
            WorkflowContext 执行上下文
        """
        # 创建上下文
        if workflow_id is None:
            workflow_id = f"wf_{int(time.time() * 1000)}"
        
        context = WorkflowContext(
            workflow_id=workflow_id,
            definition=workflow,
            variables={**workflow.variables, **(initial_vars or {})},
            start_time=time.time(),
        )
        self._contexts[workflow_id] = context
        
        # 发布开始事件
        await self.event_bus.emit(
            "workflow_started",
            {"workflow_id": workflow_id, "name": workflow.name}
        )
        
        try:
            context.status = WorkflowStatus.RUNNING
            
            # 执行所有步骤
            for i, step in enumerate(workflow.steps):
                context.current_step_index = i
                
                # 检查整体超时
                if workflow.timeout > 0:
                    if context.get_elapsed_time() > workflow.timeout:
                        raise TimeoutError(f"Workflow timeout after {workflow.timeout}s")
                
                # 执行步骤
                await self._execute_step(context, step)
                
                # 步骤失败处理
                if step.status == StepStatus.FAILED:
                    if workflow.on_failure == "abort":
                        context.status = WorkflowStatus.FAILED
                        context.error = f"Step {step.id} failed: {step.error}"
                        break
                    elif workflow.on_failure == "rollback":
                        await self._rollback(context, i)
                        context.status = WorkflowStatus.FAILED
                        context.error = f"Rolled back due to step {step.id} failure"
                        break
                    # continue: 继续执行下一步
            
            # 全部完成
            if context.status == WorkflowStatus.RUNNING:
                context.status = WorkflowStatus.COMPLETED
        
        except Exception as e:
            context.status = WorkflowStatus.FAILED
            context.error = str(e)
            logger.error(f"Workflow {workflow_id} failed: {e}\n{traceback.format_exc()}")
            
            await self.event_bus.emit(
                EventType.AGENT_ERROR,
                {"workflow_id": workflow_id, "error": str(e)}
            )
        
        finally:
            context.end_time = time.time()
            
            # 发布完成事件
            await self.event_bus.emit(
                "workflow_finished",
                {
                    "workflow_id": workflow_id,
                    "status": context.status.value,
                    "elapsed": context.get_elapsed_time(),
                }
            )
        
        return context
    
    async def _execute_step(self, context: WorkflowContext, step: WorkflowStep) -> None:
        """执行单个步骤。"""
        # 发布步骤开始事件
        await self.event_bus.emit(
            "workflow_step_started",
            {
                "workflow_id": context.workflow_id,
                "step_id": step.id,
                "step_name": step.name,
            }
        )
        
        step.status = StepStatus.RUNNING
        step.start_time = time.time()
        
        try:
            # 1. 检查条件
            if step.condition:
                if not self._evaluate_condition(step.condition, context):
                    step.status = StepStatus.SKIPPED
                    logger.info(f"Step {step.id} skipped (condition not met)")
                    return
            
            # 2. 渲染参数
            rendered_args = self._render_args(step.args, context)
            
            # 3. 执行工具调用（带重试）
            for attempt in range(step.retry + 1):
                step.attempt_count = attempt + 1
                
                if attempt > 0:
                    step.status = StepStatus.RETRYING
                    logger.info(f"Retrying step {step.id} (attempt {attempt + 1})")
                    await asyncio.sleep(step.retry_delay)
                
                try:
                    # 调用工具
                    result = await self._call_tool(
                        step.tool,
                        step.action,
                        rendered_args,
                        timeout=step.timeout
                    )
                    
                    # 成功
                    step.status = StepStatus.COMPLETED
                    step.result = result
                    
                    # 缓存结果
                    context.step_results[step.id] = {
                        "result": result,
                        "status": "success",
                    }
                    
                    break  # 成功则跳出重试循环
                
                except Exception as e:
                    step.error = str(e)
                    
                    # 最后一次重试失败
                    if attempt == step.retry:
                        step.status = StepStatus.FAILED
                        context.step_results[step.id] = {
                            "error": str(e),
                            "status": "failed",
                        }
                        raise
        
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            logger.error(f"Step {step.id} failed: {e}")
        
        finally:
            step.end_time = time.time()
            
            # 发布步骤完成事件
            await self.event_bus.emit(
                "workflow_step_finished",
                {
                    "workflow_id": context.workflow_id,
                    "step_id": step.id,
                    "status": step.status.value,
                    "elapsed": step.end_time - step.start_time,
                }
            )
    
    async def _call_tool(
        self,
        tool_name: str,
        action: str,
        args: dict[str, Any],
        timeout: float = 0,
    ) -> Any:
        """调用工具。"""
        # 构造函数名 (tool_name_action 格式)
        func_name = f"{tool_name}_{action}"
        
        # 调用工具
        if timeout > 0:
            result = await asyncio.wait_for(
                self.tool_registry.call_function(func_name, args),
                timeout=timeout
            )
        else:
            result = await self.tool_registry.call_function(func_name, args)
        
        # 解包 ToolResult
        if isinstance(result, ToolResult):
            if result.status != ToolResultStatus.SUCCESS:
                raise RuntimeError(result.error or "Tool execution failed")
            return result.data
        
        return result
    
    def _render_args(self, args: dict[str, Any], context: WorkflowContext) -> dict[str, Any]:
        """使用 Jinja2 渲染参数模板。
        
        支持语法：
        - {{ steps.step_1.result.image_path }}
        - {{ variables.user_name }}
        - {{ workflow.name }}
        """
        template_context = {
            "steps": context.step_results,
            "variables": context.variables,
            "workflow": {
                "id": context.workflow_id,
                "name": context.definition.name,
                "elapsed": context.get_elapsed_time(),
            }
        }
        
        rendered = {}
        for key, value in args.items():
            if isinstance(value, str) and "{{" in value:
                template = Template(value)
                rendered[key] = template.render(template_context)
            else:
                rendered[key] = value
        
        return rendered
    
    def _evaluate_condition(self, condition: str, context: WorkflowContext) -> bool:
        """评估条件表达式。
        
        使用 Jinja2 的条件语法。
        """
        template_context = {
            "steps": context.step_results,
            "variables": context.variables,
        }
        
        try:
            # 构造完整的 Jinja2 条件表达式
            template_str = "{% if " + condition.strip("{}").strip() + " %}True{% else %}False{% endif %}"
            template = Template(template_str)
            result = template.render(template_context).strip()
            return result == "True"
        except Exception as e:
            logger.error(f"Condition evaluation failed: {condition} -> {e}")
            return False
    
    async def _rollback(self, context: WorkflowContext, failed_step_index: int) -> None:
        """回滚已执行的步骤。"""
        logger.info(f"Rolling back workflow {context.workflow_id} from step {failed_step_index}")
        
        await self.event_bus.emit(
            "workflow_rollback_started",
            {"workflow_id": context.workflow_id, "from_step": failed_step_index}
        )
        
        # 倒序执行回滚动作
        for i in range(failed_step_index - 1, -1, -1):
            step = context.definition.steps[i]
            
            if step.rollback_action and step.status == StepStatus.COMPLETED:
                try:
                    logger.info(f"Rolling back step {step.id} with action: {step.rollback_action}")
                    # 简化：假设 rollback_action 格式为 "tool.action"
                    parts = step.rollback_action.split(".", 1)
                    if len(parts) == 2:
                        await self._call_tool(parts[0], parts[1], {})
                except Exception as e:
                    logger.error(f"Rollback failed for step {step.id}: {e}")
        
        await self.event_bus.emit(
            "workflow_rollback_finished",
            {"workflow_id": context.workflow_id}
        )
    
    # ----------------------------------------------------------------
    # 工作流控制
    # ----------------------------------------------------------------
    
    def get_context(self, workflow_id: str) -> WorkflowContext | None:
        """获取工作流上下文。"""
        return self._contexts.get(workflow_id)
    
    def list_workflows(self) -> list[str]:
        """列出所有工作流 ID。"""
        return list(self._contexts.keys())
    
    async def cancel(self, workflow_id: str) -> bool:
        """取消工作流执行。"""
        context = self._contexts.get(workflow_id)
        if not context:
            return False
        
        if context.status == WorkflowStatus.RUNNING:
            context.status = WorkflowStatus.CANCELLED
            context.end_time = time.time()
            
            await self.event_bus.emit(
                "workflow_cancelled",
                {"workflow_id": workflow_id}
            )
            return True
        
        return False
