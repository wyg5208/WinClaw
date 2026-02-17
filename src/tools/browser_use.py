"""Browser Use 工具 — AI 驱动的智能浏览器自动化。

基于 browser-use 库，让 AI 代理自主控制浏览器完成复杂任务。
相比传统 Playwright 工具，Browser Use 提供以下优势：
- 自然语言驱动：用自然语言描述任务，AI 自动规划执行
- 隐身能力强：自动绕过 CAPTCHA 和反爬虫系统
- 自适应页面：AI 理解页面结构，自动适应变化
- 多步骤任务：支持复杂的多步骤网页操作

Phase 5.x 新增功能：
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# browser-use 可用性检查
_browser_use_available: bool | None = None


def _check_browser_use() -> bool:
    """检查 browser-use 是否可用。"""
    global _browser_use_available
    if _browser_use_available is None:
        try:
            import browser_use  # noqa: F401
            _browser_use_available = True
            logger.debug("browser-use 库加载成功")
        except ImportError:
            _browser_use_available = False
            logger.debug("browser-use 不可用，请安装: pip install browser-use")
    return _browser_use_available


class BrowserUseTool(BaseTool):
    """AI 驱动的智能浏览器自动化工具。
    
    基于 browser-use 库，支持：
    - 自然语言描述任务，AI 自动执行
    - 复杂多步骤网页操作
    - 自动绕过反爬虫检测
    - 数据提取和表单填写
    
    与现有 BrowserTool 的区别：
    - BrowserTool: 传统自动化，需指定选择器和操作步骤
    - BrowserUseTool: AI 驱动，只需描述目标，自动规划执行
    """

    name = "browser_use"
    emoji = "🤖"
    title = "智能浏览器"
    description = "AI驱动的浏览器自动化：用自然语言描述任务，AI自动规划并执行网页操作"
    timeout = 300.0  # 5分钟超时，因为AI任务可能较长

    def __init__(
        self,
        headless: bool = False,
        max_steps: int = 50,
        use_vision: bool = True,
    ):
        """初始化智能浏览器工具。
        
        Args:
            headless: 是否无头模式运行
            max_steps: 最大执行步骤数
            use_vision: 是否启用视觉理解
        """
        self.headless = headless
        self.max_steps = max_steps
        self.use_vision = use_vision
        self._agent = None
        self._browser = None

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="run_task",
                description="执行智能浏览器任务。用自然语言描述要完成的任务，AI会自动规划并执行浏览器操作。",
                parameters={
                    "task": {
                        "type": "string",
                        "description": "任务描述，例如：'打开百度搜索Python教程并截图'、'登录GitHub查看今天的通知'、'在电商网站搜索最便宜的笔记本电脑'",
                    },
                    "model": {
                        "type": "string",
                        "description": "使用的LLM模型，可选：openai、anthropic、google。默认使用系统配置的模型",
                        "enum": ["openai", "anthropic", "google", "default"],
                    },
                },
                required_params=["task"],
            ),
            ActionDef(
                name="extract_data",
                description="从网页提取结构化数据。AI会自动识别页面内容并提取所需信息。",
                parameters={
                    "url": {
                        "type": "string",
                        "description": "目标网页URL",
                    },
                    "data_description": {
                        "type": "string",
                        "description": "要提取的数据描述，例如：'所有商品名称和价格'、'文章标题和摘要'",
                    },
                },
                required_params=["url", "data_description"],
            ),
            ActionDef(
                name="fill_form",
                description="智能填写网页表单。AI会自动识别表单字段并填写相应内容。",
                parameters={
                    "url": {
                        "type": "string",
                        "description": "表单页面URL",
                    },
                    "form_data": {
                        "type": "object",
                        "description": "表单数据，键值对形式，例如：{'name': '张三', 'email': 'test@example.com'}",
                    },
                    "submit": {
                        "type": "boolean",
                        "description": "是否自动提交表单（默认true）",
                    },
                },
                required_params=["url", "form_data"],
            ),
            ActionDef(
                name="navigate_and_act",
                description="导航到网页并执行指定操作。适合简单的一步操作。",
                parameters={
                    "url": {
                        "type": "string",
                        "description": "目标网页URL",
                    },
                    "action": {
                        "type": "string",
                        "description": "要执行的操作描述，例如：'点击登录按钮'、'截图保存'、'获取页面文本'",
                    },
                },
                required_params=["url", "action"],
            ),
            ActionDef(
                name="close",
                description="关闭浏览器，释放资源。",
                parameters={},
                required_params=[],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if not _check_browser_use():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="browser-use 未安装。请运行: pip install browser-use",
            )

        handlers = {
            "run_task": self._run_task,
            "extract_data": self._extract_data,
            "fill_form": self._fill_form,
            "navigate_and_act": self._navigate_and_act,
            "close": self._close_browser,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await handler(params)

    async def _get_agent(self, model: str = "default"):
        """获取或创建 browser-use Agent。
        
        Args:
            model: LLM模型类型
            
        Returns:
            Agent 实例
        """
        if self._agent is not None:
            return self._agent
            
        try:
            from browser_use import Agent
            
            # 优先使用 browser-use 内置的 ChatBrowserUse（推荐）
            # ChatBrowserUse 已内置 provider 属性，避免兼容性问题
            llm = None
            llm_provider = None  # 保存 provider 信息用于日志
            try:
                from browser_use.browser.use import ChatBrowserUse
                llm = ChatBrowserUse()
                logger.info("使用 ChatBrowserUse (browser-use 内置模型)")
                llm_provider = "browser-use"
            except ImportError:
                # 回退到 LangChain 模型，需要手动设置 provider 属性
                try:
                    if model == "anthropic":
                        from langchain_anthropic import ChatAnthropic
                        llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0.0)
                        llm_provider = "anthropic"
                    else:
                        from langchain_openai import ChatOpenAI
                        llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
                        llm_provider = "openai"
                    
                    # 关键修复：browser-use 内部检查 llm.provider 属性
                    # LangChain 的 ChatOpenAI 没有这个属性，需要手动添加
                    llm.provider = llm_provider
                    logger.info("使用 LangChain 模型: %s", llm_provider)
                except ImportError as e:
                    logger.error("导入 LangChain 模型失败: %s", e)
                    raise RuntimeError(
                        f"缺少依赖: {e}。请安装: pip install browser-use\n"
                        "或使用 browser-use 内置模型（无需额外依赖）"
                    )
            
            # 额外安全检查：确保 llm 有 provider 属性
            # 这对 browser-use 的正常运行至关重要
            if not hasattr(llm, 'provider'):
                llm.provider = llm_provider or 'openai'
                logger.warning("为 LLM 手动添加 provider 属性: %s", llm.provider)
            
            self._agent = Agent(
                task="",  # 任务在执行时设置
                llm=llm,
                use_vision=self.use_vision,
                max_actions_per_step=5,
            )
            
            logger.info("Browser Use Agent 初始化完成 (provider=%s)", llm_provider)
            return self._agent
            
        except ImportError as e:
            logger.error("导入 browser-use 失败: %s", e)
            raise RuntimeError(f"缺少依赖: {e}。请安装: pip install browser-use")

    async def _run_task(self, params: dict[str, Any]) -> ToolResult:
        """执行智能浏览器任务。"""
        task = params.get("task", "").strip()
        model = params.get("model", "default")
        
        if not task:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="任务描述不能为空",
            )
        
        try:
            agent = await self._get_agent(model)
            agent.task = task
            
            # 执行任务
            result = await agent.run(max_steps=self.max_steps)
            
            # 提取结果
            if hasattr(result, 'final_result') and result.final_result:
                output = result.final_result
            else:
                output = f"任务执行完成: {task}"
            
            logger.info("Browser Use 任务完成: %s", task[:50])
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=output,
                data={"task": task, "steps": getattr(result, 'steps_taken', 0)},
            )
            
        except Exception as e:
            logger.error("Browser Use 任务执行失败: %s", e)
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"任务执行失败: {e}",
            )

    async def _extract_data(self, params: dict[str, Any]) -> ToolResult:
        """从网页提取数据。"""
        url = params.get("url", "").strip()
        data_desc = params.get("data_description", "").strip()
        
        if not url or not data_desc:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="URL 和数据描述都不能为空",
            )
        
        # 构建任务描述
        task = f"打开 {url}，提取以下数据并以JSON格式返回: {data_desc}"
        
        try:
            agent = await self._get_agent()
            agent.task = task
            
            result = await agent.run(max_steps=self.max_steps)
            
            if hasattr(result, 'final_result') and result.final_result:
                extracted_data = result.final_result
            else:
                extracted_data = "未能提取到数据"
            
            logger.info("数据提取完成: %s", url)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"从 {url} 提取的数据:\n{extracted_data}",
                data={"url": url, "extracted": extracted_data},
            )
            
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"数据提取失败: {e}",
            )

    async def _fill_form(self, params: dict[str, Any]) -> ToolResult:
        """智能填写表单。"""
        url = params.get("url", "").strip()
        form_data = params.get("form_data", {})
        submit = params.get("submit", True)
        
        if not url or not form_data:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="URL 和表单数据都不能为空",
            )
        
        # 构建表单填写任务
        form_desc = ", ".join([f"{k}: {v}" for k, v in form_data.items()])
        submit_action = "并提交表单" if submit else "但不提交"
        
        task = f"打开 {url}，填写表单字段 ({form_desc}) {submit_action}"
        
        try:
            agent = await self._get_agent()
            agent.task = task
            
            result = await agent.run(max_steps=self.max_steps)
            
            logger.info("表单填写完成: %s", url)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已在 {url} 填写表单" + ("并提交" if submit else ""),
                data={"url": url, "form_data": form_data},
            )
            
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"表单填写失败: {e}",
            )

    async def _navigate_and_act(self, params: dict[str, Any]) -> ToolResult:
        """导航并执行操作。"""
        url = params.get("url", "").strip()
        action = params.get("action", "").strip()
        
        if not url or not action:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="URL 和操作描述都不能为空",
            )
        
        task = f"打开 {url}，然后 {action}"
        
        try:
            agent = await self._get_agent()
            agent.task = task
            
            result = await agent.run(max_steps=self.max_steps)
            
            if hasattr(result, 'final_result') and result.final_result:
                output = result.final_result
            else:
                output = f"操作完成: {action}"
            
            logger.info("导航操作完成: %s -> %s", url, action)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=output,
                data={"url": url, "action": action},
            )
            
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"操作执行失败: {e}",
            )

    async def _close_browser(self, params: dict[str, Any]) -> ToolResult:
        """关闭浏览器。"""
        if self._agent:
            try:
                # browser-use 的 Agent 可能有自己的浏览器实例
                if hasattr(self._agent, 'browser') and self._agent.browser:
                    await self._agent.browser.close()
            except Exception as e:
                logger.warning("关闭浏览器时出错: %s", e)
            finally:
                self._agent = None
        
        logger.info("Browser Use 浏览器已关闭")
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="浏览器已关闭",
        )

    async def close(self) -> None:
        """清理资源。"""
        await self._close_browser({})
