"""Shell 工具 — 在 Windows 上执行 PowerShell / CMD 命令（Phase 1.3 增强版）。

增强内容：
- 黑名单/白名单配置化（从 tools.json 加载）
- 工作目录设置
- 环境变量注入
- 白名单模式（仅允许白名单中的命令）
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# 默认危险命令关键词（兜底，tools.json 可覆盖）
_DEFAULT_BLACKLIST = [
    "format-volume",
    "format c:",
    "format d:",
    "format e:",
    "remove-item -recurse",
    "rm -rf",
    "del /s /q",
    "rd /s /q",
    "shutdown",
    "restart-computer",
    "stop-computer",
    "clear-disk",
    "diskpart",
    "reg delete",
    "new-service",
    "set-executionpolicy",
    "invoke-webrequest -outfile",
]


class ShellTool(BaseTool):
    """执行 PowerShell 或 CMD 命令。

    Phase 1.3 增强：
    - blacklist / whitelist 可通过配置注入
    - whitelist_mode 仅允许白名单中的命令
    - 支持工作目录设置
    - 支持环境变量注入
    """

    name = "shell"
    emoji = "💻"
    title = "命令行"
    description = "在 Windows 系统上执行 PowerShell 或 CMD 命令，获取命令输出结果"

    def __init__(
        self,
        timeout: int = 30,
        max_output_length: int = 10000,
        working_directory: str = "",
        env_vars: dict[str, str] | None = None,
        blacklist: list[str] | None = None,
        whitelist: list[str] | None = None,
        whitelist_mode: bool = False,
    ):
        self.timeout = timeout
        self.max_output_length = max_output_length
        self.working_directory = working_directory
        self.env_vars = env_vars or {}
        self.blacklist = blacklist if blacklist is not None else list(_DEFAULT_BLACKLIST)
        self.whitelist = whitelist or []
        self.whitelist_mode = whitelist_mode

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="run",
                description="执行一条 PowerShell 命令并返回输出。可用于查看系统信息、管理文件、运行程序等。",
                parameters={
                    "command": {
                        "type": "string",
                        "description": "要执行的 PowerShell 命令",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "命令执行的工作目录（可选，不指定则用默认工作目录）",
                    },
                },
                required_params=["command"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if action != "run":
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )

        command = params.get("command", "").strip()
        if not command:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="命令不能为空",
            )

        # 安全检查
        security_result = self._check_security(command)
        if security_result is not None:
            return security_result

        logger.info("执行命令: %s", command)

        # 构建工作目录
        cwd = params.get("working_dir", "") or self.working_directory or None
        if cwd and not os.path.isdir(cwd):
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"工作目录不存在: {cwd}",
            )

        # 构建环境变量
        env = None
        if self.env_vars:
            env = os.environ.copy()
            env.update(self.env_vars)

        try:
            proc = await asyncio.create_subprocess_exec(
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(
                status=ToolResultStatus.TIMEOUT,
                error=f"命令执行超时（{self.timeout}秒）",
            )
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"命令执行失败: {e}",
            )

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        # 截断过长的输出
        if len(stdout_text) > self.max_output_length:
            stdout_text = stdout_text[: self.max_output_length] + "\n...(输出已截断)"

        output_parts = []
        if stdout_text:
            output_parts.append(stdout_text)
        if stderr_text and proc.returncode != 0:
            output_parts.append(f"[STDERR] {stderr_text}")

        output = "\n".join(output_parts) if output_parts else "(命令执行完成，无输出)"

        if proc.returncode != 0:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                output=output,
                error=f"命令退出码: {proc.returncode}",
                data={"return_code": proc.returncode},
            )

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={"return_code": 0},
        )

    def _check_security(self, command: str) -> ToolResult | None:
        """安全检查：黑名单/白名单模式。

        Returns:
            None 表示通过，ToolResult 表示被拦截
        """
        cmd_lower = command.lower()

        # 白名单模式：只允许匹配白名单的命令
        if self.whitelist_mode and self.whitelist:
            allowed = False
            for pattern in self.whitelist:
                if pattern.lower() in cmd_lower:
                    allowed = True
                    break
            if not allowed:
                return ToolResult(
                    status=ToolResultStatus.DENIED,
                    error="命令不在白名单中，已被拦截",
                )
            return None

        # 黑名单模式（默认）
        for pattern in self.blacklist:
            if pattern.lower() in cmd_lower:
                return ToolResult(
                    status=ToolResultStatus.DENIED,
                    error=f"命令被安全策略拦截（包含危险操作: {pattern}）",
                )

        return None
