"""Browser 工具 — 基于 Playwright 的网页浏览器自动化（Sprint 2.3）。

支持动作：
- open_url: 打开 URL
- click: 点击页面元素（CSS 选择器）
- type_text: 在输入框中输入文本
- get_text: 获取页面文本内容
- screenshot: 对当前页面截图
- go_back / go_forward: 后退 / 前进
- wait: 等待指定时间或元素出现

Phase 4.7 增强：
- 空闲超时自动关闭：5分钟无操作自动释放浏览器实例
- close() 方法：确保应用退出时资源释放
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# 空闲超时时间（秒）
DEFAULT_IDLE_TIMEOUT = 300  # 5 分钟

# Playwright 延迟加载标记
_playwright_available: bool | None = None


def _check_playwright() -> bool:
    """检查 Playwright 是否可用。"""
    global _playwright_available
    if _playwright_available is None:
        try:
            import playwright  # noqa: F401
            _playwright_available = True
        except ImportError:
            _playwright_available = False
    return _playwright_available


class BrowserTool(BaseTool):
    """网页浏览器自动化工具。

    基于 Playwright，支持打开网页、点击、输入、获取文本、截图等操作。
    浏览器实例采用延迟初始化 + 复用策略，首次调用时才启动。

    Phase 4.7 增强：
    - 空闲超时自动关闭（默认 5 分钟）
    - 显式 close() 方法供应用退出时调用
    """

    name = "browser"
    emoji = "🌐"
    title = "浏览器"
    description = "自动化操作网页浏览器：打开URL、点击、输入、获取文本、截图、前进后退"

    def __init__(
        self,
        headless: bool = False,
        timeout: int = 30000,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
    ):
        self.headless = headless
        self.timeout = timeout
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.idle_timeout = idle_timeout
        # 延迟初始化
        self._playwright = None
        self._browser = None
        self._page = None
        # 空闲超时追踪
        self._last_activity_time: float = 0
        self._idle_check_task: asyncio.Task | None = None

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="open_url",
                description="在浏览器中打开指定 URL。如果浏览器未启动，会自动启动。",
                parameters={
                    "url": {
                        "type": "string",
                        "description": "要打开的网页地址（完整 URL，包含 http:// 或 https://）",
                    },
                },
                required_params=["url"],
            ),
            ActionDef(
                name="click",
                description="点击页面上的元素。通过 CSS 选择器或文本内容定位。",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "CSS 选择器，如 '#submit-btn', '.search-box', 'a[href]'",
                    },
                    "text": {
                        "type": "string",
                        "description": "按可见文本匹配元素（可选，与 selector 二选一）",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="type_text",
                description="在输入框中输入文本。先清空原有内容再输入。",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "输入框的 CSS 选择器",
                    },
                    "text": {
                        "type": "string",
                        "description": "要输入的文本内容",
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "输入后是否按回车键（默认 false）",
                    },
                },
                required_params=["selector", "text"],
            ),
            ActionDef(
                name="get_text",
                description="获取当前页面的文本内容。可指定元素选择器获取局部文本。",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "CSS 选择器（可选，不指定则获取整个页面文本）",
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "最大返回文本长度（默认 5000 字符）",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="screenshot",
                description="对当前浏览器页面截图。返回截图 base64 编码。",
                parameters={
                    "full_page": {
                        "type": "boolean",
                        "description": "是否截取整个页面（包括滚动区域）。默认 false。",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="go_back",
                description="浏览器后退到上一页。",
                parameters={},
                required_params=[],
            ),
            ActionDef(
                name="go_forward",
                description="浏览器前进到下一页。",
                parameters={},
                required_params=[],
            ),
            ActionDef(
                name="wait",
                description="等待指定时间或等待某个元素出现。",
                parameters={
                    "seconds": {
                        "type": "number",
                        "description": "等待秒数（与 selector 二选一）",
                    },
                    "selector": {
                        "type": "string",
                        "description": "等待此 CSS 选择器的元素出现（与 seconds 二选一）",
                    },
                },
                required_params=[],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if not _check_playwright():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="Playwright 未安装。请运行: pip install playwright && python -m playwright install chromium",
            )

        # 记录活动时间
        self._touch_activity()

        handlers = {
            "open_url": self._open_url,
            "click": self._click,
            "type_text": self._type_text,
            "get_text": self._get_text,
            "screenshot": self._screenshot,
            "go_back": self._go_back,
            "go_forward": self._go_forward,
            "wait": self._wait,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await handler(params)

    # ------------------------------------------------------------------
    # 浏览器生命周期
    # ------------------------------------------------------------------

    async def _ensure_browser(self) -> None:
        """确保浏览器已启动，延迟初始化。"""
        if self._page is not None:
            return

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
        )
        context = await self._browser.new_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
        )
        context.set_default_timeout(self.timeout)
        self._page = await context.new_page()
        logger.info("浏览器已启动 (headless=%s, viewport=%dx%d)",
                     self.headless, self.viewport_width, self.viewport_height)

        # 启动空闲检测任务
        self._last_activity_time = time.time()
        if self._idle_check_task is None or self._idle_check_task.done():
            self._idle_check_task = asyncio.create_task(self._idle_check_loop())

    async def _idle_check_loop(self) -> None:
        """定期检查浏览器空闲状态，超时自动关闭。"""
        while self._browser is not None:
            await asyncio.sleep(60)  # 每分钟检查一次
            if self._browser is None:
                break
            idle_time = time.time() - self._last_activity_time
            if idle_time >= self.idle_timeout:
                logger.info("浏览器空闲超过 %d 秒，自动关闭", self.idle_timeout)
                await self.close()
                break

    def _touch_activity(self) -> None:
        """更新最后活动时间。"""
        self._last_activity_time = time.time()

    async def close(self) -> None:
        """关闭浏览器，释放资源。"""
        # 取消空闲检测任务
        if self._idle_check_task and not self._idle_check_task.done():
            self._idle_check_task.cancel()
            try:
                await self._idle_check_task
            except asyncio.CancelledError:
                pass

        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._page = None
        logger.info("浏览器已关闭")

    # ------------------------------------------------------------------
    # 动作实现
    # ------------------------------------------------------------------

    async def _open_url(self, params: dict[str, Any]) -> ToolResult:
        url = params.get("url", "").strip()
        if not url:
            return ToolResult(status=ToolResultStatus.ERROR, error="URL 不能为空")

        # 自动补全协议
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        await self._ensure_browser()
        try:
            response = await self._page.goto(url, wait_until="domcontentloaded")
            status = response.status if response else "unknown"
            title = await self._page.title()
            logger.info("打开页面: %s (状态: %s)", url, status)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已打开: {url}\n页面标题: {title}\nHTTP 状态: {status}",
                data={"url": url, "title": title, "http_status": status},
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"打开页面失败: {e}")

    async def _click(self, params: dict[str, Any]) -> ToolResult:
        selector = params.get("selector", "")
        text = params.get("text", "")

        if not selector and not text:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="必须提供 selector 或 text 参数",
            )

        await self._ensure_browser()
        try:
            if text:
                await self._page.get_by_text(text, exact=False).first.click()
                desc = f"文本 '{text}'"
            else:
                await self._page.click(selector)
                desc = f"选择器 '{selector}'"

            # 等待页面可能的导航
            await self._page.wait_for_load_state("domcontentloaded")
            title = await self._page.title()
            logger.info("点击元素: %s", desc)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已点击: {desc}\n当前页面: {title}",
                data={"title": title},
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"点击失败: {e}")

    async def _type_text(self, params: dict[str, Any]) -> ToolResult:
        selector = params.get("selector", "")
        text = params.get("text", "")
        press_enter = params.get("press_enter", False)

        if not selector or not text:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="必须提供 selector 和 text 参数",
            )

        await self._ensure_browser()
        try:
            await self._page.fill(selector, text)
            if press_enter:
                await self._page.press(selector, "Enter")
                await self._page.wait_for_load_state("domcontentloaded")
            logger.info("输入文本到 '%s': %s", selector, text[:50])
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已在 '{selector}' 输入: {text}" + (" (并按回车)" if press_enter else ""),
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"输入失败: {e}")

    async def _get_text(self, params: dict[str, Any]) -> ToolResult:
        selector = params.get("selector", "")
        max_length = params.get("max_length", 5000)

        await self._ensure_browser()
        try:
            if selector:
                element = self._page.locator(selector).first
                text = await element.inner_text()
            else:
                text = await self._page.inner_text("body")

            if len(text) > max_length:
                text = text[:max_length] + f"\n...(已截断，共 {len(text)} 字符)"

            title = await self._page.title()
            logger.info("获取文本: %d 字符", len(text))
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"页面: {title}\n\n{text}",
                data={"title": title, "length": len(text)},
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"获取文本失败: {e}")

    async def _screenshot(self, params: dict[str, Any]) -> ToolResult:
        full_page = params.get("full_page", False)

        await self._ensure_browser()
        try:
            img_bytes = await self._page.screenshot(full_page=full_page, type="png")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            title = await self._page.title()
            size_kb = len(img_bytes) / 1024
            logger.info("页面截图: %s (%.1fKB)", title, size_kb)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已截图: {title} ({size_kb:.1f}KB)",
                data={"base64": img_b64, "title": title, "size_bytes": len(img_bytes)},
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"截图失败: {e}")

    async def _go_back(self, params: dict[str, Any]) -> ToolResult:
        await self._ensure_browser()
        try:
            await self._page.go_back(wait_until="domcontentloaded")
            title = await self._page.title()
            url = self._page.url
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已后退到: {title} ({url})",
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"后退失败: {e}")

    async def _go_forward(self, params: dict[str, Any]) -> ToolResult:
        await self._ensure_browser()
        try:
            await self._page.go_forward(wait_until="domcontentloaded")
            title = await self._page.title()
            url = self._page.url
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已前进到: {title} ({url})",
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"前进失败: {e}")

    async def _wait(self, params: dict[str, Any]) -> ToolResult:
        seconds = params.get("seconds")
        selector = params.get("selector")

        if not seconds and not selector:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="必须提供 seconds 或 selector 参数",
            )

        await self._ensure_browser()
        try:
            if selector:
                await self._page.wait_for_selector(selector, state="visible")
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=f"元素 '{selector}' 已出现",
                )
            else:
                await asyncio.sleep(float(seconds))
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=f"已等待 {seconds} 秒",
                )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"等待失败: {e}")
