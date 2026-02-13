"""Search 工具 — 本地文件搜索 + Web 搜索（Sprint 2.3）。

支持动作：
- local_search: 本地文件名/内容搜索（glob 遍历）
- web_search: Web 搜索（使用 DuckDuckGo HTML 解析，无需 API Key）
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class SearchTool(BaseTool):
    """本地文件搜索 + Web 搜索工具。"""

    name = "search"
    emoji = "🔍"
    title = "搜索"
    description = "搜索本地文件（按文件名或内容）和 Web 网页搜索"

    def __init__(
        self,
        max_local_results: int = 50,
        max_web_results: int = 10,
        local_max_depth: int = 5,
        web_timeout: int = 10,
        search_engine: str = "auto",  # auto, bing, baidu, duckduckgo
        max_results_per_page: int = 50,  # 单次最大结果数（Bing限制）
    ):
        self.max_local_results = max_local_results
        self.max_web_results = max_web_results
        self.local_max_depth = local_max_depth
        self.web_timeout = web_timeout
        self.search_engine = search_engine
        self.max_results_per_page = max_results_per_page

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="local_search",
                description="在本地目录中搜索文件。支持按文件名模式（glob）或文件内容关键词搜索。",
                parameters={
                    "directory": {
                        "type": "string",
                        "description": "搜索起始目录路径",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "文件名匹配模式（glob 格式，如 '*.pdf', '*.txt', 'report*'）",
                    },
                    "content": {
                        "type": "string",
                        "description": "搜索文件内容中包含的关键词（可选，与 pattern 可同时使用）",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "最大搜索目录深度（默认5）",
                    },
                },
                required_params=["directory"],
            ),
            ActionDef(
                name="web_search",
                description="在互联网上搜索信息。使用搜索引擎查找相关网页，返回标题、摘要和链接。",
                parameters={
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回结果数（默认10，最多50）",
                        "default": 10,
                    },
                    "page": {
                        "type": "integer",
                        "description": "页码（从1开始，默认1），用于翻页查看更多结果",
                        "default": 1,
                    },
                },
                required_params=["query"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "local_search": self._local_search,
            "web_search": self._web_search,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await handler(params)

    # ------------------------------------------------------------------
    # local_search
    # ------------------------------------------------------------------

    async def _local_search(self, params: dict[str, Any]) -> ToolResult:
        directory = params.get("directory", "").strip()
        pattern = params.get("pattern", "*")
        content_keyword = params.get("content", "").strip()
        max_depth = params.get("max_depth", self.local_max_depth)

        if not directory:
            return ToolResult(status=ToolResultStatus.ERROR, error="搜索目录不能为空")

        search_dir = Path(directory).expanduser().resolve()
        if not search_dir.exists():
            return ToolResult(status=ToolResultStatus.ERROR, error=f"目录不存在: {search_dir}")
        if not search_dir.is_dir():
            return ToolResult(status=ToolResultStatus.ERROR, error=f"路径不是目录: {search_dir}")

        results: list[dict[str, Any]] = []

        def _walk(dir_path: Path, depth: int) -> None:
            if depth > max_depth or len(results) >= self.max_local_results:
                return
            try:
                for entry in sorted(dir_path.iterdir(), key=lambda p: p.name.lower()):
                    if len(results) >= self.max_local_results:
                        return
                    if entry.is_dir():
                        # 跳过隐藏目录和常见无关目录
                        if entry.name.startswith(".") or entry.name in (
                            "__pycache__", "node_modules", ".git", "venv", ".venv"
                        ):
                            continue
                        _walk(entry, depth + 1)
                    elif entry.is_file():
                        if not fnmatch.fnmatch(entry.name.lower(), pattern.lower()):
                            continue

                        file_info: dict[str, Any] = {
                            "path": str(entry),
                            "name": entry.name,
                            "size": entry.stat().st_size,
                        }

                        # 内容搜索
                        if content_keyword:
                            try:
                                text = entry.read_text(encoding="utf-8", errors="ignore")
                                if content_keyword.lower() not in text.lower():
                                    continue
                                # 找到匹配的行
                                matched_lines = []
                                for i, line in enumerate(text.splitlines(), 1):
                                    if content_keyword.lower() in line.lower():
                                        matched_lines.append(f"  L{i}: {line.strip()[:100]}")
                                        if len(matched_lines) >= 3:
                                            break
                                file_info["matched_lines"] = matched_lines
                            except (UnicodeDecodeError, PermissionError, OSError):
                                continue

                        results.append(file_info)
            except PermissionError:
                pass

        # 在线程中执行文件遍历以避免阻塞
        await asyncio.get_event_loop().run_in_executor(None, _walk, search_dir, 1)

        if not results:
            msg = f"在 {search_dir} 中未找到匹配的文件"
            if pattern != "*":
                msg += f"（模式: {pattern}）"
            if content_keyword:
                msg += f"（内容含: {content_keyword}）"
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=msg,
                data={"results": [], "count": 0},
            )

        lines = [f"在 {search_dir} 中找到 {len(results)} 个匹配文件:\n"]
        for r in results:
            size = r["size"]
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1_048_576:
                size_str = f"{size / 1024:.1f}KB"
            else:
                size_str = f"{size / 1_048_576:.1f}MB"

            lines.append(f"  📄 {r['name']} ({size_str})")
            lines.append(f"     {r['path']}")
            if "matched_lines" in r:
                for ml in r["matched_lines"]:
                    lines.append(f"    {ml}")

        if len(results) >= self.max_local_results:
            lines.append(f"\n  ...(达到上限 {self.max_local_results}，可能还有更多)")

        logger.info("本地搜索: %s pattern=%s content=%s → %d 结果",
                     search_dir, pattern, content_keyword or "(无)", len(results))
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={"results": [{"path": r["path"], "name": r["name"]} for r in results],
                  "count": len(results)},
        )

    # ------------------------------------------------------------------
    # web_search
    # ------------------------------------------------------------------

    async def _web_search(self, params: dict[str, Any]) -> ToolResult:
        query = params.get("query", "").strip()
        max_results = params.get("max_results", self.max_web_results)
        page = params.get("page", 1)

        if not query:
            return ToolResult(status=ToolResultStatus.ERROR, error="搜索关键词不能为空")

        # 限制参数范围
        max_results = max(1, min(max_results, self.max_results_per_page))
        page = max(1, min(page, 10))  # 最多10页

        # 尝试多个搜索引擎
        engines = []
        if self.search_engine == "auto":
            # 优先Bing（最稳定），其次百度，最后DuckDuckGo
            engines = ["bing", "baidu", "duckduckgo"]
        else:
            engines = [self.search_engine]

        results = []
        last_error = None
        
        for engine in engines:
            try:
                logger.info("尝试使用 %s 搜索 (page=%d, max_results=%d)...", engine, page, max_results)
                fetch_func = getattr(self, f"_fetch_{engine}", None)
                if fetch_func is None:
                    continue
                    
                results = await asyncio.get_event_loop().run_in_executor(
                    None, fetch_func, query, max_results, page
                )
                
                if results:
                    logger.info("%s 搜索成功: '%s' → %d 结果", engine, query, len(results))
                    break
            except Exception as e:
                last_error = e
                logger.warning("%s 搜索失败: %s", engine, e)
                continue

        if not results:
            error_msg = f"所有搜索引擎均失败"
            if last_error:
                error_msg += f": {last_error}"
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=error_msg,
                output="建议: 1. 检查网络连接 2. 尝试使用代理 3. 稍后重试",
            )

        lines = [f"搜索 '{query}' 的结果 (共 {len(results)} 条):\n"]
        if page > 1:
            lines[0] = f"搜索 '{query}' 的结果 - 第 {page} 页 (共 {len(results)} 条):\n"
        
        for i, r in enumerate(results, 1):
            lines.append(f"  {i}. {r['title']}")
            lines.append(f"     {r['url']}")
            if r.get("snippet"):
                lines.append(f"     {r['snippet'][:150]}")
            lines.append("")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={
                "results": results, 
                "count": len(results), 
                "engine": engine,
                "page": page,
                "max_results": max_results,
                "has_more": len(results) >= max_results,  # 可能还有更多结果
            },
        )

    def _fetch_bing(self, query: str, max_results: int, page: int = 1) -> list[dict[str, str]]:
        """通过 Bing 搜索（无需 API Key）。
        
        Args:
            query: 搜索关键词
            max_results: 每页结果数
            page: 页码（从1开始）
        """
        encoded_query = urllib.parse.quote_plus(query)
        
        # 计算偏移量: Bing 使用 first 参数 (0, 10, 20, ...)
        first = (page - 1) * max_results
        url = f"https://www.bing.com/search?q={encoded_query}&count={max_results}&first={first}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self.web_timeout) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning("Bing 请求失败: %s", e)
            raise

        results: list[dict[str, str]] = []

        # Bing 结果解析 - 更灵活的匹配
        # 先查找所有 b_algo 结果块
        algo_blocks = re.findall(
            r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>',
            html,
            re.DOTALL,
        )

        for block in algo_blocks[:max_results]:
            # 提取标题和URL
            title_match = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not title_match:
                continue
            
            href = title_match.group(1)
            title_html = title_match.group(2)
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            
            # 提取摘要 - 尝试多种方式
            snippet = ""
            
            # 方式1: 查找 <p> 标签
            p_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
            if p_match:
                snippet = re.sub(r"<[^>]+>", "", p_match.group(1)).strip()
            
            # 方式2: 查找 class 包含 caption 或 description
            if not snippet:
                desc_match = re.search(r'class="[^"]*(?:caption|description)[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
                if desc_match:
                    snippet = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip()

            if title and href and href.startswith("http"):
                results.append({
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                })

        return results

    def _fetch_baidu(self, query: str, max_results: int, page: int = 1) -> list[dict[str, str]]:
        """通过百度搜索（无需 API Key）。
        
        Args:
            query: 搜索关键词
            max_results: 每页结果数
            page: 页码（从1开始）
        """
        encoded_query = urllib.parse.quote(query)
        
        # 计算偏移量: 百度使用 pn 参数 (0, 10, 20, ...)
        pn = (page - 1) * max_results
        url = f"https://www.baidu.com/s?wd={encoded_query}&rn={max_results}&pn={pn}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self.web_timeout) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning("百度请求失败: %s", e)
            raise

        results: list[dict[str, str]] = []

        # 百度结果解析 - 更宽松的匹配
        # 匹配各种版本的百度结果页面
        result_blocks = re.findall(
            r'<div[^>]*class="[^"]*result[^"]*"[^>]*>.*?<h3[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?</h3>(.*?)</div>',
            html,
            re.DOTALL,
        )

        for href, title_html, content_html in result_blocks[:max_results * 3]:  # 多抽取一些,过滤后可能不够
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            
            # 提取摘要（可能在不同的标签中）
            snippet = ""
            snippet_match = re.search(r'class="[^"]*abstract[^"]*"[^>]*>(.*?)</div>', content_html, re.DOTALL)
            if snippet_match:
                snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip()
            else:
                # 备选：直接从 content 中提取
                snippet = re.sub(r"<[^>]+>", "", content_html).strip()[:200]

            # 过滤广告和无效链接
            if not title or len(title) < 3:
                continue
            if "广告" in title or "推广" in title:
                continue
            
            # 处理百度重定向链接
            real_url = href
            if "baidu.com" in href and ("link?" in href or "baidu.php" in href):
                # 尝试提取真实 URL
                url_match = re.search(r"url=([^&]+)", href)
                if url_match:
                    try:
                        real_url = urllib.parse.unquote(url_match.group(1))
                    except Exception:
                        pass
                # 如果仍然是百度链接,保留原始链接
                if not real_url.startswith("http") or "baidu.com" in real_url:
                    real_url = href

            if title:
                results.append({
                    "title": title,
                    "url": real_url,
                    "snippet": snippet,
                })
                
            if len(results) >= max_results:
                break

        return results

    def _fetch_duckduckgo(self, query: str, max_results: int, page: int = 1) -> list[dict[str, str]]:
        """通过 DuckDuckGo HTML 页面解析搜索结果（无需 API Key）。
        
        注: DuckDuckGo HTML 版本不支持分页,只能返回第一页。
        """
        if page > 1:
            # DuckDuckGo HTML 版不支持分页
            return []
            
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self.web_timeout) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning("DuckDuckGo 请求失败: %s", e)
            raise

        results: list[dict[str, str]] = []

        # 解析搜索结果 — DuckDuckGo HTML 版本的结构
        # 每个结果在 <a class="result__a" href="...">title</a> 和 <a class="result__snippet">snippet</a>
        result_blocks = re.findall(
            r'<a\s+rel="nofollow"\s+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
            r'.*?<a\s+class="result__snippet"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )

        for href, title_html, snippet_html in result_blocks[:max_results]:
            # 清理 HTML 标签
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()

            # DuckDuckGo 的 href 是重定向链接，尝试提取真实 URL
            real_url = href
            uddg_match = re.search(r"uddg=([^&]+)", href)
            if uddg_match:
                real_url = urllib.parse.unquote(uddg_match.group(1))

            if title and real_url:
                results.append({
                    "title": title,
                    "url": real_url,
                    "snippet": snippet,
                })

        return results
